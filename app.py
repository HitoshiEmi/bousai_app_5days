from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from urllib.parse import urlparse, urljoin
from functools import wraps
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

# app.py はプロジェクト直下に置く。
# 実体（templates / static / data）は bousai_app/ 配下にあるので、そこを参照する。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, 'bousai_app')

app = Flask(
    __name__,
    template_folder=os.path.join(APP_DIR, 'templates'),
    static_folder=os.path.join(APP_DIR, 'static'),
)
app.secret_key = 'your-secret-key-here'

# 管理者認証情報
ADMIN_CREDENTIALS = {
    'admin': '123'
}

# ────────────────────────────────
# 気象警報・注意報設定
PREFECTURE_CODE = "020000"  # 青森県
AREA_NAME = "青森市"

# ワークショップ課題：青森市の市区町村コードに変更する
AREA_CODE = "1420500"

WARNING_URL = (
    f"https://www.jma.go.jp/bosai/warning/data/r8/{PREFECTURE_CODE}.json"
)

JST = timezone(timedelta(hours=9))

# 警報・注意報のコード一覧
WARNING_CODES = {
    "00": "解除",
    "02": "暴風雪警報",
    "03": "大雨警報",
    "04": "洪水警報",
    "05": "暴風警報",
    "06": "大雪警報",
    "07": "波浪警報",
    "08": "高潮警報",
    "09": "土砂災害警戒情報",
    "10": "大雨注意報",
    "12": "大雪注意報",
    "13": "風雪注意報",
    "14": "雷注意報",
    "15": "強風注意報",
    "16": "波浪注意報",
    "17": "融雪注意報",
    "18": "洪水注意報",
    "19": "高潮注意報",
    "20": "濃霧注意報",
    "21": "乾燥注意報",
    "22": "なだれ注意報",
    "23": "低温注意報",
    "24": "霜注意報",
    "25": "着氷注意報",
    "26": "着雪注意報",
    "27": "その他の注意報",
    "29": "土砂災害警戒情報",
    "32": "暴風雪特別警報",
    "33": "大雨特別警報",
    "35": "暴風特別警報",
    "36": "大雪特別警報",
    "37": "波浪特別警報",
    "38": "高潮特別警報",
    "39": "土砂災害特別警報",
    "43": "大雨警報",
    "48": "高潮警報",
    "49": "土砂災害警戒情報"
}

# ────────────────────────────────
# サンプルデータの読み込み
DATA_FILE = os.path.join(APP_DIR, 'data', 'shelters.json')
INSTRUCTIONS_FILE = os.path.join(APP_DIR, 'data', 'instructions.json')

def load_json(path, default):
    """JSONファイルを読み込む（存在しない・壊れている場合は default を返す）"""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

shelters = load_json(DATA_FILE, [])
instructions = load_json(INSTRUCTIONS_FILE, [])

def save_instructions():
    """指示ボードのデータをファイルに保存する"""
    try:
        with open(INSTRUCTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(instructions, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def save_shelters():
    """避難所データをJSONファイルに保存する"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(shelters, f, ensure_ascii=False, indent=2)

SHELTER_STATUSES = ('開設中', '未開設', '閉鎖')
SHELTER_EQUIPMENT = ('バリアフリー', '仕切り壁', 'ペット避難可', '多目的トイレ', '授乳スペース')
SHELTER_SUPPLIES = ('粉ミルク', '哺乳瓶', 'おむつ', '生理用品', '飲料水', '食料', '毛布')

def shelter_form_data(source=None):
    """フォーム送信値または避難所データを画面用の辞書に整える"""
    source = source or {}
    return {
        'name': str(source.get('name', '')).strip(),
        'address': str(source.get('address', '')).strip(),
        'capacity': str(source.get('capacity', '')).strip(),
        'status': str(source.get('status', '')).strip(),
        'equipment': source.get('equipment', []),
        'supplies': source.get('supplies', []),
    }

def validate_shelter_form(form):
    """避難所登録フォームを検証し、画面表示用エラーを返す"""
    errors = {}
    if not form['name']:
        errors['name'] = '避難所名を入力してください。'
    if not form['address']:
        errors['address'] = '住所を入力してください。'
    if not form['capacity']:
        errors['capacity'] = '避難可能人数を入力してください。'
    else:
        try:
            if int(form['capacity']) < 1:
                errors['capacity'] = '避難可能人数は1以上の数値で入力してください。'
        except ValueError:
            errors['capacity'] = '避難可能人数は1以上の数値で入力してください。'
    if form['status'] not in SHELTER_STATUSES:
        errors['status'] = '開設状況を選択してください。'
    return errors
# ────────────────────────────────

# ────────────────────────────────
# 認証関連の設定とヘルパー関数
def is_safe_url(target):
    """リダイレクト先URLが安全かどうかチェック"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

def login_required(f):
    """認証が必要なページに付けるデコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            # 現在のURLをnextパラメータとしてログイン画面にリダイレクト
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def get_japan_time():
    """日本時間（JST）の現在時刻を取得する"""
    return datetime.now(JST).strftime("%Y年%m月%d日 %H:%M")


def format_report_time(iso_str):
    """気象庁の発表時刻（ISO形式）をJSTの表示用文字列に変換する"""
    if not iso_str:
        return "不明"
    try:
        parsed = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        if parsed.tzinfo:
            parsed = parsed.astimezone(JST)
        return parsed.strftime("%Y年%m月%d日 %H:%M")
    except ValueError:
        return iso_str


def filter_shelters(district=None):
    """district 指定があれば一致する避難所のみ、なければ全件を返す"""
    return [s for s in shelters if not district or s.get('district') == district]


def parse_area_warnings(warning_data):
    """最新発表から対象市区町村の警報・注意報を抽出する"""
    if not isinstance(warning_data, list):
        raise ValueError("気象庁の警報・注意報データが新形式の配列ではありません")

    warnings = []
    report_datetimes = []

    reports = [report for report in warning_data if isinstance(report, dict)]
    latest_report = max(
        reports,
        key=lambda report: report.get("reportDatetime", "")
    ) if reports else {}

    for report in reports:
        report_datetime = report.get("reportDatetime")
        if isinstance(report_datetime, str) and report_datetime:
            report_datetimes.append(report_datetime)

    warning = latest_report.get("warning", {})
    class20_items = warning.get("class20Items", [])
    area = next(
        (
            item for item in class20_items
            if isinstance(item, dict)
            and item.get("areaCode") == AREA_CODE
        ),
        None
    )
    if not area:
        return warnings, max(report_datetimes, default="")

    kinds = area.get("kinds", [])
    if not isinstance(kinds, list):
        return warnings, max(report_datetimes, default="")

    for kind in kinds:
        if not isinstance(kind, dict):
            continue

        status = kind.get("status", "")
        code = kind.get("code", "")
        if status not in ("発表", "継続") or not code:
            continue

        warnings.append({
            "name": WARNING_CODES.get(
                code,
                f"警報・注意報（コード: {code}）"
            ),
            "code": code,
            "status": status
        })

    latest_report_datetime = max(report_datetimes, default="")
    return warnings, latest_report_datetime


def get_weather_warnings():
    """対象市区町村の警報・注意報を取得する"""
    try:
        # 青森県の新形式（令和8年～）警報・注意報データを取得
        with urllib.request.urlopen(url=WARNING_URL, timeout=10) as res:
            warning_data = json.loads(res.read())

        warnings, report_datetime = parse_area_warnings(warning_data)

        return {
            "area_name": AREA_NAME,
            "warnings": warnings,
            "report_time": format_report_time(report_datetime),
            "last_fetch_time": get_japan_time()
        }

    except Exception:
        return {
            "area_name": AREA_NAME,
            "warnings": [],
            "report_time": "取得失敗",
            "last_fetch_time": get_japan_time(),
            "error": True
        }


# トップページ：templates/index.html を返す（住民向け指示も表示する）
@app.route('/')
def index():
    resident_notices = [i for i in instructions if i.get('target') == '住民']
    return render_template(
        'index.html',
        resident_notices=resident_notices,
        shelters=shelters
    )

# ログインページ
@app.route('/login', methods=['GET', 'POST'])
def login():
    # リダイレクト先を取得（デフォルトは避難所登録画面）
    next_url = request.args.get('next') or request.form.get('next')

    # 安全でないURLの場合はデフォルトページにリダイレクト
    if not next_url or not is_safe_url(next_url):
        next_url = url_for('shelter_register')

    if request.method == 'POST':
        password = request.form.get('password', '').strip()

        # 認証チェック
        username = next(
            (name for name, registered_password in ADMIN_CREDENTIALS.items()
             if registered_password == password),
            None
        )
        if username:
            session['logged_in'] = True
            session['username'] = username
            # ログイン成功後は指定されたページにリダイレクト
            return redirect(next_url)
        return render_template('login.html', error=True, message="パスワードが正しくありません。", next=next_url)

    # ログイン済みの場合は指定されたページにリダイレクト
    if session.get('logged_in'):
        return redirect(next_url)

    return render_template('login.html', next=next_url)

# ログアウト
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# 避難所登録ページ
@app.route('/shelter_register', methods=['GET', 'POST'])
@login_required
def shelter_register():
    form_data = shelter_form_data(request.form)
    editing_id = request.form.get('editing_id', '').strip()
    selected_id = request.form.get('shelter_id', '').strip()
    message = None
    message_type = None
    field_errors = {}

    if request.method == 'POST' and request.form.get('action') == 'load':
        if not selected_id:
            message = '更新する避難所を選択してください。'
            message_type = 'error'
        else:
            selected_shelter = next(
                (shelter for shelter in shelters if str(shelter.get('id')) == selected_id),
                None
            )
            if not selected_shelter:
                message = '更新対象の避難所が見つかりません。'
                message_type = 'error'
            else:
                form_data = shelter_form_data(selected_shelter)
                editing_id = selected_id
                message = '更新する避難所の登録内容を読み込みました。'
                message_type = 'success'

    elif request.method == 'POST' and request.form.get('action') == 'save':
        form_data = shelter_form_data(request.form)
        form_data['equipment'] = [item for item in request.form.getlist('equipment') if item in SHELTER_EQUIPMENT]
        form_data['supplies'] = [item for item in request.form.getlist('supplies') if item in SHELTER_SUPPLIES]
        field_errors = validate_shelter_form(form_data)

        if not field_errors:
            shelter_values = {
                'name': form_data['name'],
                'address': form_data['address'],
                'capacity': form_data['capacity'],
                'status': form_data['status'],
                'equipment': form_data['equipment'],
                'supplies': form_data['supplies'],
            }
            target_shelter = None
            original_shelter = None
            if editing_id:
                target_shelter = next(
                    (shelter for shelter in shelters if str(shelter.get('id')) == editing_id),
                    None
                )
                if not target_shelter:
                    message = '更新対象の避難所が見つかりません。'
                    message_type = 'error'
                else:
                    original_shelter = target_shelter.copy()
            if message_type != 'error':
                try:
                    if target_shelter:
                        target_shelter.update(shelter_values)
                        message = '避難所の登録内容を更新しました。'
                    else:
                        next_id = max(
                            (shelter.get('id', 0) for shelter in shelters),
                            default=0
                        ) + 1
                        shelters.append({'id': next_id, **shelter_values})
                        message = '避難所の登録が完了しました。'
                        editing_id = ''
                    save_shelters()
                    message_type = 'success'
                except (OSError, TypeError, ValueError):
                    if target_shelter:
                        target_shelter.clear()
                        target_shelter.update(original_shelter)
                    elif shelters and shelters[-1].get('name') == shelter_values['name']:
                        shelters.pop()
                    message = '避難所情報を保存できませんでした。'
                    message_type = 'error'

    return render_template(
        'shelter_register.html',
        shelters=shelters,
        form_data=form_data,
        editing_id=editing_id,
        selected_id=selected_id,
        field_errors=field_errors,
        message=message,
        message_type=message_type,
        statuses=SHELTER_STATUSES,
        equipment_options=SHELTER_EQUIPMENT,
        supply_options=SHELTER_SUPPLIES,
        current_time=get_japan_time()
    )

# 避難所検索ページ
@app.route('/shelter_search')
def shelter_search():
    return render_template('shelter_search.html')

# 全施設一覧ページ
@app.route('/all_shelters')
def all_shelters():
    return render_template(
        'search_results.html',
        results=shelters,
        equipment_options=SHELTER_EQUIPMENT
    )


# 指示ボード：住民向けの指示を一覧で確認する
@app.route('/board')
@login_required
def board():
    resident_instructions = [i for i in instructions if i.get('target') == '住民']
    return render_template('board.html', instructions=resident_instructions)

# 検索結果ページ：templates/search_results.html を返す
@app.route('/search_results')
def search_results():
    results = filter_shelters(request.args.get('district'))
    return render_template(
        'search_results.html',
        results=results,
        equipment_options=SHELTER_EQUIPMENT
    )

# JSON API：/shelters?district=地区名
@app.route('/shelters', methods=['GET'])
def get_shelters():
    results = filter_shelters(request.args.get('district'))

    if not results:
        # 見つからなければエラー JSON を返す
        return jsonify({'error': 'No shelters found'}), 404

    # 見つかったらリストを JSON で返す
    return jsonify(results)

# 気象警報・注意報API
@app.route('/api/weather_warnings')
def api_weather_warnings():
    """気象警報・注意報をJSON形式で返すAPI"""
    return jsonify(get_weather_warnings())

if __name__ == '__main__':
    app.run(debug=True, port=5000)
