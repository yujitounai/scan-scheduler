import uuid
import threading
from datetime import datetime,timezone
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import time
import logging
import requests, json
import os
from zoneinfo import ZoneInfo
from sqlalchemy import Column, String, Boolean
import difflib

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///scans.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ログ設定（詳細なログをコンソールへ出力）
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# モデル定義
class Scan(db.Model):
    __tablename__ = 'scans'
    id = db.Column(db.String, primary_key=True)
    domain = db.Column(db.String, nullable=False)
    status = db.Column(db.String, nullable=False)
    result = db.Column(db.String)
    # ここでスケジュール実行であれば関連するスケジュールのIDを記録
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedules.id'), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    has_diff = db.Column(db.Boolean, default=False)
    
class ScanResult(db.Model):
    __tablename__ = 'scan_results'
    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.String, db.ForeignKey('scans.id'), nullable=False)
    tool_name = db.Column(db.String, nullable=False)
    target = db.Column(db.String, nullable=False)
    result = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    
# 新たにスケジュール用のモデルを定義
class Schedule(db.Model):
    __tablename__ = 'schedules'
    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String, nullable=False)
    tool_name = db.Column(db.String, nullable=False)
    schedule_type = db.Column(db.String, nullable=False)
    schedule_value = db.Column(db.String, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    last_run = db.Column(db.DateTime)
    compare_mode = db.Column(db.String, default="none")  # none, diff, json_keys
    last_diff_at = db.Column(db.DateTime, nullable=True)  # 差分があった最後のスキャン時刻
    last_diff_acknowledged_at = db.Column(db.DateTime, nullable=True)  # ユーザーが最後にアラート確認した時刻


# APScheduler の初期化
scheduler = BackgroundScheduler(timezone="Asia/Tokyo")
scheduler.start()
logger.info("Scheduler started in PID %s", os.getpid())
logger.info("Existing jobs after start: %s", scheduler.get_jobs())

# 入力値の検証と CronTrigger の生成
def validate_and_create_trigger(schedule_type, schedule_value):
    value = schedule_value.strip()
    if schedule_type == "daily":
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("毎日のスケジュール値は 'HH:MM' の形式で入力してください (例: 14:30)")
        hour = int(parts[0].strip())
        minute = int(parts[1].strip())
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("時刻が正しくありません。")
        return CronTrigger(hour=hour, minute=minute, timezone=ZoneInfo("Asia/Tokyo"))
    elif schedule_type == "weekly":
        parts = value.split()
        if len(parts) != 2:
            raise ValueError("毎週のスケジュール値は '曜日 HH:MM' の形式で入力してください (例: mon 14:30)")
        day_of_week = parts[0].strip().lower()
        if day_of_week not in ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']:
            raise ValueError("曜日が正しくありません (例: mon)")
        time_parts = parts[1].split(":")
        if len(time_parts) != 2:
            raise ValueError("時刻部分の形式が正しくありません (例: 14:30)")
        hour = int(time_parts[0].strip())
        minute = int(time_parts[1].strip())
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("時刻が正しくありません。")
        return CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute, timezone=ZoneInfo("Asia/Tokyo"))
    elif schedule_type == "monthly":
        parts = value.split()
        if len(parts) != 2:
            raise ValueError("毎月のスケジュール値は '日 HH:MM' の形式で入力してください (例: 1 14:30)")
        day = int(parts[0].strip())
        if not (1 <= day <= 31):
            raise ValueError("日付は1～31の値で入力してください。")
        time_parts = parts[1].split(":")
        if len(time_parts) != 2:
            raise ValueError("時刻部分の形式が正しくありません (例: 14:30)")
        hour = int(time_parts[0].strip())
        minute = int(time_parts[1].strip())
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("時刻が正しくありません。")
        return CronTrigger(day=day, hour=hour, minute=minute, timezone=ZoneInfo("Asia/Tokyo"))
    elif schedule_type == "hourly":
        try:
            minute = int(value)
        except Exception:
            raise ValueError("毎時のスケジュール値は 0～59 の数値で入力してください (例: 30)")
        if not (0 <= minute <= 59):
            raise ValueError("毎時のスケジュール値は 0～59 の数値で入力してください (例: 30)")
        return CronTrigger(minute=minute)
    else:
        raise ValueError("不明なスケジュールタイプです")

# add_schedule_job は既に検証済みのトリガーを受け取ってジョブ登録するだけにします
def add_schedule_job(schedule, trigger):
    app.logger.info("生成された CronTrigger: %s", trigger)
    scheduler.add_job(
        func=scheduled_scan_job,
        trigger=trigger,
        args=[schedule.id],
        id=f"schedule_{schedule.id}",
        replace_existing=True
    )
    job = scheduler.get_job(f"schedule_{schedule.id}")
    app.logger.info(
        "ジョブ schedule_%s が追加/更新されました → next run at %s",
        schedule.id,
        job.next_run_time
    )

# スケジュール実行時のジョブ関数
def scheduled_scan_job(schedule_id):
    logger.info(
        ">>> scheduled_scan_job triggered for schedule_id=%s at %s",
        schedule_id,
        datetime.now().isoformat()
    )
    with app.app_context():
        schedule = Schedule.query.get(schedule_id)
        if schedule and schedule.is_active:
            new_job_id = str(uuid.uuid4())
            # schedule_id カラムにスケジュールの ID をセット
            new_scan = Scan(id=new_job_id, domain=schedule.domain, status="pending", schedule_id=schedule.id)
            db.session.add(new_scan)
            db.session.commit()
            threading.Thread(target=update_scan_job, args=(new_job_id, schedule.domain, schedule.tool_name, None)).start()
            schedule.last_run = datetime.now()
            db.session.commit()

def compare_scan_results(prev_result, curr_result, mode="diff", keys=None):
    if mode == "none":
        return None
    if mode == "diff":
        return "".join(difflib.unified_diff(
            prev_result.splitlines(keepends=True),
            curr_result.splitlines(keepends=True),
            fromfile='previous', tofile='current'
        ))
    if mode == "json_keys" and keys:
        try:
            import json
            prev_data = json.loads(prev_result)
            curr_data = json.loads(curr_result)
            prev_filtered = {k: prev_data.get(k) for k in keys}
            curr_filtered = {k: curr_data.get(k) for k in keys}
            if prev_filtered != curr_filtered:
                return f"差分あり\nBefore: {prev_filtered}\nAfter: {curr_filtered}"
        except Exception as e:
            return f"JSON比較エラー: {e}"
    return None
    
# アプリケーション起動時
with app.app_context():
    db.create_all()
    for sch in Schedule.query.filter_by(is_active=True).all():
        trigger = validate_and_create_trigger(sch.schedule_type, sch.schedule_value)
        add_schedule_job(sch, trigger)
    logger.debug("Database tables created (if not exist).")

# スキャン結果を保存するヘルパー関数
def save_scan_result(scan_id, tool_name, target, result):
    logger.debug("Saving scan result: scan_id=%s, tool=%s, target=%s", scan_id, tool_name, target)
    new_result = ScanResult(scan_id=scan_id, tool_name=tool_name, target=target, result=result)
    db.session.add(new_result)
    db.session.commit()

import requests, json

def update_scan_job(job_id, domain, tool_name, template=None):
    logger.info(f"スキャン処理開始: job_id={job_id}, domain={domain}, tool_name={tool_name}, template={template}")
    
    try:
        if tool_name == "nmap":
            scan_url = "http://amass-api:5555/nmap"
            payload = {"target": domain}
        elif tool_name == "amass":
            scan_url = "http://amass-api:5555/amass"
            payload = {"target": domain}
        elif tool_name == "recon-ng":
            scan_url = "http://amass-api:5555/recon"
            payload = {"target": domain}
        elif tool_name == "subfinder":
            scan_url = "http://pd-api:5556/subfinder"
            payload = {"target": domain}
        elif tool_name in ["httpx", "dnsx", "naabu", "cdncheck", "tlsx"]:
            scan_url = f"http://pd-api:5556/{tool_name}"
            payload = {"target": domain}
        elif tool_name == "nuclei":
            scan_url = "http://nuclei-api:5557/nuclei"
            payload = {"target": domain, "template": template}
        elif tool_name == "pipeline":
            scan_url = "http://pd-api:5556/pipeline"
            payload = {"target": domain}
        else:
            scan_url = "http://pd-api:5556/dummy"
            payload = {"target": domain}
        
        logger.info(f"外部スキャンサービスにリクエスト送信: {scan_url}, payload={payload}")
        response = requests.post(scan_url, json=payload)
        response.raise_for_status()
        result_data = response.json()
        logger.info(f"外部サービスからの初期応答: {result_data}")
        
        external_job_id = result_data.get("job_id")
        if not external_job_id:
            raise ValueError("外部ジョブIDが返されませんでした")
        
        poll_url = f"{scan_url}/{external_job_id}"
        max_retries = 300
        output = ""
        for i in range(max_retries):
            poll_response = requests.get(poll_url)
            poll_response.raise_for_status()
            poll_data = poll_response.json()
            logger.debug(f"ポーリング応答({i+1}回目): {poll_data}")
            if poll_data.get("status") == "completed":
                res = poll_data.get("result")
                if res:
                    # nuclei や pipeline の場合、結果の "results" キーを優先して取得する
                    if tool_name in ["nuclei", "pipeline"] and "results" in res:
                        output = json.dumps(res["results"], ensure_ascii=False, indent=2)
                    else:
                        if res.get("returncode", 1) == 0:
                            output = "\n".join(res.get("stdout", [])) if isinstance(res.get("stdout"), list) else res.get("stdout", "")
                        else:
                            output = res.get("stderr", "エラーが発生しました")
                else:
                    output = "結果なし"
                break
            else:
                time.sleep(2)
        else:
            output = "外部スキャンサービスからの結果が取得できませんでした"
    except Exception as e:
        output = f"Error: {str(e)}"
        logger.error(f"スキャンサービス実行エラー: {e}")
    
    with app.app_context():
        try:
            scan = Scan.query.get(job_id)
            if scan:
                scan.status = "completed"
                scan.result = output
                db.session.commit()
                logger.info(f"スキャン処理完了: job_id={job_id}, result={output}")
            else:
                logger.error(f"スキャンジョブが見つかりません: job_id={job_id}")
        except Exception as e:
            logger.error(f"スキャンジョブ更新エラー: {e}")

        # このブロック内で save_scan_result を呼び出す
        try:
            save_scan_result(job_id, tool_name, domain, output)
            try:
                schedule = Schedule.query.get(scan.schedule_id)
                if schedule and schedule.compare_mode != "none":
                    prev = Scan.query \
                        .filter(Scan.schedule_id == schedule.id, Scan.id != scan.id, Scan.status == "completed") \
                        .order_by(Scan.created_at.desc()) \
                        .first()
                    if prev and prev.result:
                        keys = ["status_code", "tech", "content_length"] if schedule.compare_mode == "json_keys" else None
                        diff = compare_scan_results(prev.result, scan.result, schedule.compare_mode, keys)
                        if diff:
                            logger.info(f"比較差分あり (mode={schedule.compare_mode}):\n{diff}")
                            scan.has_diff = True
                            db.session.commit()
            except Exception as e:
                logger.warning(f"比較処理中にエラー: {e}")
        except Exception as e:
            logger.error(f"スキャン結果保存エラー: {e}")
        # update_scan_job の中に比較処理と last_diff_at の更新を追加
        # ※ 以下は scan.result を保存した直後に入れる
        try:
            schedule = Schedule.query.get(scan.schedule_id)
            if schedule and schedule.compare_mode != "none":
                prev = Scan.query \
                    .filter(Scan.schedule_id == schedule.id, Scan.id != scan.id, Scan.status == "completed") \
                    .order_by(Scan.created_at.desc()) \
                    .first()
                if prev and prev.result:
                    keys = ["status_code", "tech", "content_length"] if schedule.compare_mode == "json_keys" else None
                    diff = compare_scan_results(prev.result, scan.result, schedule.compare_mode, keys)
                    if diff:
                        logger.info(f"比較差分あり (mode={schedule.compare_mode}):\n{diff}")
                        scan.has_diff = True
                        schedule.last_diff_at = scan.created_at
                        db.session.commit()
        except Exception as e:
            logger.warning(f"比較処理中にエラー: {e}")



@app.route('/trigger_scan', methods=['POST'])
def trigger_scan():
    data = request.get_json()
    domain = data.get('domain')
    tool = data.get('tool')
    template = data.get('template')  # nuclei 用のテンプレート情報も受け取る
    if not domain or not tool:
        logger.error("domain or tool not provided: %s", data)
        return jsonify({"error": "ドメインとツールは必須です"}), 400

    job_id = str(uuid.uuid4())
    logger.info(f"トリガースキャン開始: job_id={job_id}, domain={domain}, tool={tool}, template={template}")

    try:
        scan = Scan(id=job_id, domain=domain, status="pending")
        db.session.add(scan)
        db.session.commit()
        # nuclei の場合は template を update_scan_job に渡す（それ以外は None）
        threading.Thread(target=update_scan_job, args=(job_id, domain, tool, template)).start()
        return jsonify({"job_id": job_id}), 202
    except Exception as e:
        logger.error(f"トリガースキャンエラー: {str(e)}")
        return jsonify({"error": str(e)}), 500


# 既存のスキャン状態取得、結果取得エンドポイントはそのまま利用
@app.route('/scan_status/<job_id>')
def scan_status(job_id):
    scan = Scan.query.filter_by(id=job_id).first()
    if scan:
        logger.debug("Returning status for job_id=%s", job_id)
        return jsonify({
            "job_id": scan.id,
            "domain": scan.domain,
            "status": scan.status,
            "result": scan.result
        })
    else:
        logger.error("Scan job not found: job_id=%s", job_id)
        return jsonify({"error": "ジョブが見つかりません"}), 404

@app.route('/save_scan_result', methods=['POST'])
def save_scan_result_endpoint():
    data = request.json
    scan_id = data.get('scan_id')
    tool_name = data.get('tool_name')
    target = data.get('target')
    result = data.get('result')

    if not all([scan_id, tool_name, target, result]):
        logger.error("Missing parameters when saving scan result: %s", data)
        return jsonify({"error": "必要なパラメータが不足しています"}), 400

    save_scan_result(scan_id, tool_name, target, result)
    return jsonify({"status": "success"})

@app.route('/scan_results')
def get_scan_results():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    tool_name = request.args.get('tool_name')
    target = request.args.get('target')

    query = ScanResult.query
    if tool_name:
        query = query.filter_by(tool_name=tool_name)
    if target:
        query = query.filter(ScanResult.target.like(f'%{target}%'))

    query = query.order_by(ScanResult.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    results = pagination.items

    formatted_results = []
    for r in results:
        try:
            parsed = json.loads(r.result) if r.result else None
        except Exception:
            parsed = None

        formatted_results.append({
            'id': r.id,
            'scan_id': r.scan_id,
            'tool_name': r.tool_name,
            'target': r.target,
            'result': r.result,
            'parsed_result': parsed,
            'created_at': r.created_at.isoformat() if r.created_at else None
        })

    logger.debug("Returning %d scan results", len(formatted_results))
    return jsonify({
        'results': formatted_results,
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'total_pages': pagination.pages
    })

@app.route('/scan_results/<int:result_id>')
def get_scan_result_detail(result_id):
    result = ScanResult.query.get(result_id)
    if result:
        logger.debug("Returning detail for scan result id=%d", result_id)
        try:
            parsed = json.loads(result.result) if result.result else None
        except Exception:
            parsed = None

        return jsonify({
            'id': result.id,
            'scan_id': result.scan_id,
            'tool_name': result.tool_name,
            'target': result.target,
            'result': result.result,
            'parsed_result': parsed,
            'created_at': result.created_at.isoformat() if result.created_at else None
        })
    else:
        logger.error("Scan result not found: id=%d", result_id)
        return jsonify({"error": "結果が見つかりません"}), 404

@app.route('/scan_results/tools')
def get_scan_tools():
    tools = db.session.query(ScanResult.tool_name.distinct()).order_by(ScanResult.tool_name).all()
    tools_list = [tool[0] for tool in tools]
    logger.debug("Available scan tools: %s", tools_list)
    return jsonify(tools_list)

@app.route('/results')
def results_page():
    logger.debug("Rendering results.html")
    return render_template('results.html')

@app.route('/')
def index():
    logger.debug("Rendering index.html")
    return render_template('index.html')


# スケジュール新規作成API（POST /api/schedules）
@app.route('/api/schedules', methods=['POST'])
def create_schedule():
    data = request.get_json()
    domain = data.get("domain")
    tool_name = data.get("tool_name")
    schedule_type = data.get("schedule_type")
    schedule_value = data.get("schedule_value")
    compare_mode = data.get("compare_mode", "none")

    try:
        trigger = validate_and_create_trigger(schedule_type, schedule_value)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    schedule = Schedule(
        domain=domain,
        tool_name=tool_name,
        schedule_type=schedule_type,
        schedule_value=schedule_value,
        is_active=True,
        compare_mode=compare_mode
    )
    db.session.add(schedule)
    db.session.commit()

    try:
        add_schedule_job(schedule, trigger)
    except Exception as e:
        return jsonify({"error": "ジョブ登録エラー: " + str(e)}), 500

    return jsonify({"status": "success", "id": schedule.id})


# GET /api/schedules
@app.route('/api/schedules', methods=['GET'])
def get_schedules():
    schedules = Schedule.query.all()
    data = []
    for sch in schedules:
        job = scheduler.get_job(f"schedule_{sch.id}")
        next_run = job.next_run_time.astimezone(timezone.utc).isoformat() if job and job.next_run_time else None
        last_run = sch.last_run.astimezone(timezone.utc).isoformat() if sch.last_run else None
        last_diff_at = sch.last_diff_at.isoformat() if sch.last_diff_at else None
        last_diff_ack = sch.last_diff_acknowledged_at.isoformat() if sch.last_diff_acknowledged_at else None

        alert_needed = (
            sch.last_diff_at is not None and
            (sch.last_diff_acknowledged_at is None or sch.last_diff_acknowledged_at < sch.last_diff_at)
        )

        data.append({
            "id": sch.id,
            "domain": sch.domain,
            "tool_name": sch.tool_name,
            "schedule_type": sch.schedule_type,
            "schedule_value": sch.schedule_value,
            "is_active": sch.is_active,
            "last_run": last_run,
            "next_run": next_run,
            "compare_mode": sch.compare_mode,
            "last_diff_at": last_diff_at,
            "last_diff_acknowledged_at": last_diff_ack,
            "alert_needed": alert_needed
        })
    return jsonify(data)


@app.route('/api/schedules/<int:schedule_id>', methods=['GET'])
def get_schedule(schedule_id):
    schedule = Schedule.query.get(schedule_id)
    if not schedule:
        return jsonify({"error": "スケジュールが見つかりません"}), 404
    data = {
        "id": schedule.id,
        "domain": schedule.domain,
        "tool_name": schedule.tool_name,
        "schedule_type": schedule.schedule_type,
        "schedule_value": schedule.schedule_value,
        "is_active": schedule.is_active,
        "last_run": schedule.last_run.isoformat() if schedule.last_run else None,
        "compare_mode": schedule.compare_mode
    }
    return jsonify(data)

# /api/schedules/<int:schedule_id>/acknowledge 差分確認API
@app.route('/api/schedules/<int:schedule_id>/acknowledge', methods=['POST'])
def acknowledge_schedule_diff(schedule_id):
    schedule = Schedule.query.get(schedule_id)
    if not schedule:
        return jsonify({"error": "スケジュールが見つかりません"}), 404

    schedule.last_diff_acknowledged_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"status": "acknowledged", "schedule_id": schedule.id})


# API エンドポイント例（スケジュール更新）
@app.route('/api/schedules/<int:schedule_id>', methods=['PUT'])
def update_schedule(schedule_id):
    data = request.get_json()
    schedule = Schedule.query.get(schedule_id)
    if not schedule:
        return jsonify({"error": "スケジュールが見つかりません"}), 404

    schedule.domain = data.get("domain", schedule.domain)
    schedule.tool_name = data.get("tool_name", schedule.tool_name)
    schedule.schedule_type = data.get("schedule_type", schedule.schedule_type)
    schedule.schedule_value = data.get("schedule_value", schedule.schedule_value)
    schedule.is_active = data.get("is_active", schedule.is_active)
    schedule.compare_mode = data.get("compare_mode", schedule.compare_mode)
    db.session.commit()

    if schedule.is_active:
        try:
            trigger = validate_and_create_trigger(schedule.schedule_type, schedule.schedule_value)
            add_schedule_job(schedule, trigger)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    else:
        job_id = f"schedule_{schedule.id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

    return jsonify({"status": "success"})

# API エンドポイント例（スケジュール削除）
@app.route('/api/schedules/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    schedule = Schedule.query.get(schedule_id)
    if not schedule:
        return jsonify({"error": "スケジュールが見つかりません"}), 404
    try:
        scheduler.remove_job(f"schedule_{schedule.id}")
    except Exception:
        # ジョブが存在しない場合も無視
        pass
    db.session.delete(schedule)
    db.session.commit()
    return jsonify({"status": "deleted"})

# app.py の該当部分を以下のように書き換えます

from flask import jsonify
import json

@app.route('/api/schedules/<int:schedule_id>/results', methods=['GET'])
def get_schedule_results(schedule_id):
    schedule = Schedule.query.get(schedule_id)
    if not schedule:
        return jsonify({"error": "スケジュールが見つかりません"}), 404

    page     = request.args.get('page',     1,  type=int)
    per_page = request.args.get('per_page', 10, type=int)

    pagination = Scan.query \
        .filter_by(schedule_id=schedule_id) \
        .order_by(Scan.created_at.desc()) \
        .paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for s in pagination.items:
        try:
            parsed = json.loads(s.result) if s.result else None
        except Exception:
            parsed = None

        items.append({
            "scan_id":       s.id,
            "domain":        s.domain,
            "status":        s.status,
            "result":        s.result,
            "parsed_result": parsed,
            "created_at":    s.created_at.isoformat() if s.created_at else None,
            "has_diff":      s.has_diff
        })

    return jsonify({
        "results":      items,
        "total":        pagination.total,
        "page":         pagination.page,
        "per_page":     pagination.per_page,
        "total_pages":  pagination.pages
    })



@app.route('/api/schedules/tools', methods=['GET'])
def get_tools():
    # ここでは、利用可能なスキャンツールの一覧を固定で返す例
    # 必要に応じてデータベースや設定ファイルから取得するように変更可能です
    tools = ["nmap", "amass", "recon-ng", "subfinder", "httpx", "dnsx", "naabu", "cdncheck", "tlsx", "nuclei", "pipeline"]
    return jsonify(tools)

@app.route('/schedules')
def schedules_page():
    return render_template('schedules.html')

if __name__ == "__main__":
    logger.debug("Starting Flask application on port 3333")
    app.run(host="0.0.0.0", port=3333, debug=True, use_reloader=False)
