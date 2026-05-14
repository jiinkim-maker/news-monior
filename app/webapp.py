from flask import Flask, render_template, request, redirect, url_for, g, jsonify
from datetime import datetime, timedelta, timezone
from app.db import (
    init_db,
    get_user_by_username,
    list_keyword_rules,
    create_keyword_rule,
    delete_keyword_rule,
    update_keyword_rule_active,
    get_active_keyword_rules,
    create_keyword_analysis_run,
    create_keyword_analysis_article,
    get_latest_keyword_analysis_run,
    get_keyword_analysis_articles_by_run,
    get_recent_keyword_analysis_runs,
    get_recent_keyword_analysis_articles,
    create_media_analysis_run,
    create_media_analysis_item,
    get_latest_media_analysis_run,
    get_media_analysis_items_by_run,
    get_recent_media_analysis_items,
    create_banner_monitor_run,
    create_banner_monitor_snapshot,
    get_latest_banner_monitor_run,
    get_banner_monitor_snapshots_by_run,
    get_banner_monitor_snapshots_by_code,
    create_user,
    list_users,
    update_user_password,
    find_users_by_display_name,
    get_user_by_id,
    delete_user_by_id,
    get_bookmark_level,
    cycle_bookmark_level,
    list_bookmarked_articles,
    get_shared_bookmark,
    get_shared_bookmark_level,
    save_shared_bookmark,
    list_shared_bookmarks,
    get_banner_monitor_snapshot_by_id,
)

from app.auth import (
    login_user,
    logout_user,
    get_current_user,
    login_required,
    inject_current_user,
)
from app.utils.security import verify_password, hash_password
from app.keyword_engine import analyze_shortlink_batch
from app.media_engine import analyze_media_shortlink_batch
from app.monitor_targets import build_monitor_targets
from app.banner_monitor_engine import analyze_banner_monitor_target, compare_slot_items
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = "news-monitor-session-secret-key"

init_db()
MONITOR_TARGETS = build_monitor_targets()

############ 내부 운영 코드 ##############
INTERNAL_OPERATION_CODE = "cheilnews!"
########################################


def format_display_datetime(value):
    if not value:
        return "-"

    try:
        if isinstance(value, str):
            dt = datetime.fromisoformat(value)
        else:
            dt = value
    except Exception:
        return str(value).replace("T", " ")

    return dt.strftime("%Y-%m-%d %H:%M:%S")

@app.before_request
def before_request():
    inject_current_user()


@app.context_processor
def inject_template_globals():
    return {
        "current_user": g.get("current_user"),
        "format_display_datetime": format_display_datetime,
    }


def current_username():
    user = get_current_user()
    return user["username"] if user else "system"


def admin_required():
    user = get_current_user()
    return bool(user and user.get("role") == "admin")


def find_monitor_target_by_code(code: str):
    for item in MONITOR_TARGETS:
        if item["code"] == code:
            return item
    return None


def snapshot_has_kv(snapshot: dict) -> bool:
    return bool(snapshot.get("kv_items"))


def snapshot_has_banner(snapshot: dict) -> bool:
    return bool(snapshot.get("banner_items"))


def find_previous_snapshot_with_kv(history: list[dict], current_index: int):
    for i in range(current_index + 1, len(history)):
        if snapshot_has_kv(history[i]):
            return history[i]
    return None


def find_previous_snapshot_with_banner(history: list[dict], current_index: int):
    for i in range(current_index + 1, len(history)):
        if snapshot_has_banner(history[i]):
            return history[i]
    return None


def summarize_compare_result(compare_result: dict):
    slot_results = compare_result.get("slot_results", [])
    image_changed = sum(1 for item in slot_results if item.get("image_changed"))
    landing_changed = sum(1 for item in slot_results if item.get("landing_changed"))
    title_changed = sum(1 for item in slot_results if item.get("title_changed"))
    error_count = sum(1 for item in slot_results if item.get("landing_error"))

    return {
        "changed_slots": compare_result.get("changed_count", 0),
        "image_changed": image_changed,
        "landing_changed": landing_changed,
        "title_changed": title_changed,
        "error_count": error_count,
    }


def build_monitor_status_map():
    status_map = {}

    for target in MONITOR_TARGETS:
        history = get_banner_monitor_snapshots_by_code(target["code"], limit=20)

        if not history:
            status_map[target["code"]] = {
                "has_snapshot": False,
                "latest_checked_at": "-",
                "has_change": False,
                "kv_changed_count": 0,
                "banner_changed_count": 0,
            }
            continue

        latest = history[0]
        run_type = latest.get("run_type", "")

        kv_changed_count = 0
        banner_changed_count = 0

        if run_type in ("scan_all", "scan_all_kv", "scan_filtered_kv", "scan_one_kv") and snapshot_has_kv(latest):
            prev_kv = find_previous_snapshot_with_kv(history, 0)
            if prev_kv:
                kv_compare = compare_slot_items(prev_kv["kv_items"], latest["kv_items"])
                kv_changed_count = kv_compare["changed_count"]

        if run_type in ("scan_all", "scan_all_banner", "scan_filtered_banner", "scan_one_banner") and snapshot_has_banner(latest):
            prev_banner = find_previous_snapshot_with_banner(history, 0)
            if prev_banner:
                banner_compare = compare_slot_items(prev_banner["banner_items"], latest["banner_items"])
                banner_changed_count = banner_compare["changed_count"]

        status_map[target["code"]] = {
            "has_snapshot": True,
            "latest_checked_at": format_display_datetime(latest["created_at"]),
            "has_change": (kv_changed_count > 0 or banner_changed_count > 0),
            "kv_changed_count": kv_changed_count,
            "banner_changed_count": banner_changed_count,
        }

    return status_map


def build_latest_banner_run_summary():
    latest_run = get_latest_banner_monitor_run()
    if not latest_run:
        return {
            "has_run": False,
            "run_at": "-",
            "run_type_label": "-",
            "scope_label": "-",
            "target_count": 0,
            "changed_targets": 0,
            "kv_stats": None,
            "banner_stats": None,
        }

    latest_snapshots = get_banner_monitor_snapshots_by_run(latest_run["id"])
    run_type = latest_run.get("run_type", "")

    run_type_label_map = {
        "scan_all": "전체 검사",
        "scan_all_banner": "전체 배너 검사",
        "scan_all_kv": "전체 KV 검사",
        "scan_filtered_banner": "선택 권역/조건 배너 검사",
        "scan_filtered_kv": "선택 권역/조건 KV 검사",
        "scan_one_banner": "국가별 배너 검사",
        "scan_one_kv": "국가별 KV 검사",
    }
    run_type_label = run_type_label_map.get(run_type, run_type)

    scope_label = "전체 국가"
    if run_type in ("scan_one_banner", "scan_one_kv"):
        target = find_monitor_target_by_code(latest_run.get("target_code") or "")
        scope_label = target["country"] if target else (latest_run.get("target_code") or "-")
    elif run_type in ("scan_filtered_banner", "scan_filtered_kv"):
        scope_label = latest_run.get("target_code") or "현재 필터 대상"

    kv_stats = {
        "changed_slots": 0,
        "image_changed": 0,
        "landing_changed": 0,
        "title_changed": 0,
        "error_count": 0,
    }
    banner_stats = {
        "changed_slots": 0,
        "image_changed": 0,
        "landing_changed": 0,
        "title_changed": 0,
        "error_count": 0,
    }

    changed_targets = 0

    for snap in latest_snapshots:
        code = snap["code"]
        history = get_banner_monitor_snapshots_by_code(code, limit=20)
        current_index = next((i for i, item in enumerate(history) if item["id"] == snap["id"]), None)
        if current_index is None:
            continue

        target_changed = False

        if run_type in ("scan_all", "scan_all_kv", "scan_filtered_kv", "scan_one_kv") and snapshot_has_kv(snap):
            prev_kv = find_previous_snapshot_with_kv(history, current_index)
            if prev_kv:
                kv_compare = compare_slot_items(prev_kv["kv_items"], snap["kv_items"])
                kv_summary = summarize_compare_result(kv_compare)
                for key in kv_stats:
                    kv_stats[key] += kv_summary[key]
                if kv_summary["changed_slots"] > 0:
                    target_changed = True

        if run_type in ("scan_all", "scan_all_banner", "scan_filtered_banner", "scan_one_banner") and snapshot_has_banner(snap):
            prev_banner = find_previous_snapshot_with_banner(history, current_index)
            if prev_banner:
                banner_compare = compare_slot_items(prev_banner["banner_items"], snap["banner_items"])
                banner_summary = summarize_compare_result(banner_compare)
                for key in banner_stats:
                    banner_stats[key] += banner_summary[key]
                if banner_summary["changed_slots"] > 0:
                    target_changed = True

        if target_changed:
            changed_targets += 1

    if run_type in ("scan_all_banner", "scan_filtered_banner", "scan_one_banner"):
        kv_stats = None
    if run_type in ("scan_all_kv", "scan_filtered_kv", "scan_one_kv"):
        banner_stats = None

    return {
        "has_run": True,
        "run_at": format_display_datetime(latest_run["created_at"]),
        "run_type_label": run_type_label,
        "scope_label": scope_label,
        "target_count": latest_run["total_targets"],
        "changed_targets": changed_targets,
        "kv_stats": kv_stats,
        "banner_stats": banner_stats,
    }

def extract_country_code_from_url(url: str) -> str:
    if not url:
        return "-"

    try:
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if not parts:
            return "-"
        return parts[0].upper()
    except Exception:
        return "-"
    

def build_media_page_context(latest_run: dict | None, latest_items: list[dict]):
    grouped_articles = []
    media_heatmap_groups = []

    total_image = 0
    total_gif = 0
    total_mp4 = 0
    total_embedded = 0
    total_error_items = 0
    total_no_media = 0

    article_map = {}

    for item in latest_items:
        short_url = item.get("short_url") or "-"
        article_title = item.get("article_title") or "-"
        group_key = f"{short_url}||{article_title}"
        media_type = (item.get("media_type") or "").lower()
        country_code = extract_country_code_from_url(item.get("long_url"))
        error_text = (item.get("error") or "").strip()

        is_no_media = error_text.lower() == "no media found"
        has_real_error = bool(error_text) and not is_no_media

        if media_type == "image":
            total_image += 1
        elif media_type == "gif":
            total_gif += 1
        elif media_type == "mp4":
            total_mp4 += 1
        elif media_type == "embedded_video":
            total_embedded += 1

        if has_real_error:
            total_error_items += 1

        if group_key not in article_map:
            article_map[group_key] = {
                "group_key": group_key,
                "short_url": short_url,
                "article_title": article_title,
                "country_code": country_code,
                "items": [],
                "max_width": 0,
                "max_height": 0,
                "max_size_bytes": 0,
                "media_types": set(),
                "has_error": False,
                "has_no_media": False,
            }

        group = article_map[group_key]
        group["items"].append(item)
        group["has_error"] = group["has_error"] or has_real_error
        group["has_no_media"] = group["has_no_media"] or is_no_media

        width = item.get("width") or 0
        height = item.get("height") or 0
        size_bytes = item.get("size_bytes") or 0

        group["max_width"] = max(group["max_width"], width)
        group["max_height"] = max(group["max_height"], height)
        group["max_size_bytes"] = max(group["max_size_bytes"], size_bytes)

        if media_type:
            group["media_types"].add(media_type)

    for index, group in enumerate(article_map.values(), start=1):
        group["rowspan"] = len(group["items"])
        group["media_type_filter_value"] = ",".join(sorted(group["media_types"]))
        group["article_no"] = index

        grouped_articles.append(group)

        if group["has_no_media"]:
            total_no_media += 1

        blocks = []
        for media in group["items"]:
            media_type = (media.get("media_type") or "").lower()
            error_text = (media.get("error") or "").strip()
            is_no_media = error_text.lower() == "no media found"
            has_real_error = bool(error_text) and not is_no_media

            if is_no_media:
                tone_class = "tone-no-media"
            elif media_type == "image":
                tone_class = "tone-image"
            elif media_type == "mp4":
                tone_class = "tone-mp4"
            elif media_type == "gif":
                tone_class = "tone-gif"
            elif media_type == "embedded_video":
                tone_class = "tone-embedded"
            else:
                tone_class = "tone-other"

            blocks.append({
                "tone_class": tone_class,
                "media_type": media_type or "-",
                "filename": media.get("filename") or "-",
                "has_error": has_real_error,
                "is_no_media": is_no_media,
            })

        media_heatmap_groups.append({
            "group_key": group["group_key"],
            "article_no": group["article_no"],
            "country_code": group["country_code"],
            "short_url": group["short_url"],
            "article_title": group["article_title"],
            "blocks": blocks,
        })

    summary_boxes = [
        {
            "label": "Articles",
            "value": len(grouped_articles),
        },
        {
            "label": "Total Media",
            "value": (latest_run or {}).get("total_media_count", 0),
        },
        {
            "label": "Errors",
            "value": total_error_items,
        },
        {
            "label": "No Media",
            "value": total_no_media,
        },
    ]

    media_type_counts = {
        "image": total_image,
        "gif": total_gif,
        "mp4": total_mp4,
        "embedded": total_embedded,
        "error": total_error_items,
        "no_media": total_no_media,
    }

    return {
        "summary_boxes": summary_boxes,
        "grouped_articles": grouped_articles,
        "media_heatmap_groups": media_heatmap_groups,
        "media_type_counts": media_type_counts,
    }


def build_history_page_context(recent_runs: list[dict], recent_articles: list[dict]):
    runs_with_display = []
    run_articles_map = {}
    article_history_map = {}
    latest_articles = []

    for idx, run in enumerate(recent_runs, start=1):
        item = dict(run)
        item["no"] = idx
        item["display_created_at"] = format_display_datetime(item.get("created_at"))
        runs_with_display.append(item)

    for article in recent_articles:
        item = dict(article)
        item["display_created_at"] = format_display_datetime(item.get("created_at"))

        run_key = str(item.get("run_id") or "")
        if run_key not in run_articles_map:
            run_articles_map[run_key] = []
        run_articles_map[run_key].append(item)

    article_key_order = []
    seen_article_key = set()

    for article in recent_articles:
        item = dict(article)
        item["display_created_at"] = format_display_datetime(item.get("created_at"))

        short_url = (item.get("short_url") or "").strip()
        article_key = short_url if short_url else f"__title__::{item.get('title') or ''}"

        if article_key not in article_history_map:
            article_history_map[article_key] = []

        article_history_map[article_key].append(item)

        if article_key not in seen_article_key:
            seen_article_key.add(article_key)
            article_key_order.append(article_key)

    limited_article_keys = article_key_order[:150]

    for idx, article_key in enumerate(limited_article_keys, start=1):
        latest_item = article_history_map[article_key][0]
        item = dict(latest_item)
        item["no"] = idx
        item["article_key"] = article_key

        bookmark = get_shared_bookmark(f"article::{article_key}") or {}
        item["bookmark_level"] = bookmark.get("bookmark_level", 0) or 0
        item["bookmark_note"] = bookmark.get("note", "") or ""

        latest_articles.append(item)

    return {
        "recent_runs": runs_with_display,
        "latest_articles": latest_articles,
        "run_articles_map": run_articles_map,
        "article_history_map": article_history_map,
    }


@app.route("/")
def home():
    if get_current_user():
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user():
        return redirect(url_for("dashboard"))

    error_message = None

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        user = get_user_by_username(username)

        if not user:
            error_message = "아이디 또는 비밀번호가 올바르지 않습니다."
        elif not user.get("is_active"):
            error_message = "비활성화된 계정입니다."
        elif not verify_password(password, user["password_hash"]):
            error_message = "아이디 또는 비밀번호가 올바르지 않습니다."
        else:
            login_user(user)
            return redirect(url_for("dashboard"))

    return render_template("login.html", error_message=error_message)


@app.route("/recover-password", methods=["GET", "POST"])
def recover_password():
    if get_current_user():
        return redirect(url_for("dashboard"))

    error_message = None
    success_message = None
    temp_password = None
    pending_username = None
    pending_temp_password = None

    if request.method == "POST":
        action = (request.form.get("action") or "validate").strip()

        if action == "validate":
            recover_identity = (request.form.get("recover_identity") or "").strip()
            operation_code = (request.form.get("operation_code") or "").strip()

            user = get_user_by_username(recover_identity)

            if not user:
                matched_users = find_users_by_display_name(recover_identity)

                if len(matched_users) == 1:
                    user = matched_users[0]
                elif len(matched_users) > 1:
                    error_message = "동일한 이름의 계정이 2개 이상 있습니다. ID로 진행해 주세요."

            if not error_message:
                if not user:
                    error_message = "일치하는 계정을 찾을 수 없습니다."
                elif operation_code != INTERNAL_OPERATION_CODE:
                    error_message = "내부 운영 코드가 올바르지 않습니다."
                else:
                    pending_username = user["username"]
                    pending_temp_password = f"Temp{user['username']}!"

        elif action == "issue":
            pending_username = (request.form.get("pending_username") or "").strip()
            pending_temp_password = (request.form.get("pending_temp_password") or "").strip()
            operation_code = (request.form.get("operation_code") or "").strip()

            user = get_user_by_username(pending_username)

            if not user:
                error_message = "일치하는 계정을 찾을 수 없습니다."
            elif operation_code != INTERNAL_OPERATION_CODE:
                error_message = "내부 운영 코드가 올바르지 않습니다."
            elif not pending_temp_password:
                error_message = "임시 비밀번호 생성 정보가 올바르지 않습니다."
            else:
                update_user_password(pending_username, hash_password(pending_temp_password))
                temp_password = pending_temp_password
                success_message = "임시 비밀번호가 발급되었습니다. 아래 비밀번호를 복사해 사용해 주세요."
                pending_username = None
                pending_temp_password = None

    return render_template(
        "recover_password.html",
        error_message=error_message,
        success_message=success_message,
        temp_password=temp_password,
        pending_username=pending_username,
        pending_temp_password=pending_temp_password,
    )

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    latest_keyword_run = get_latest_keyword_analysis_run()
    latest_keyword_articles = []
    if latest_keyword_run:
        latest_keyword_articles = get_keyword_analysis_articles_by_run(latest_keyword_run["id"])

    latest_media_run = get_latest_media_analysis_run()
    latest_media_items = []
    if latest_media_run:
        latest_media_items = get_media_analysis_items_by_run(latest_media_run["id"])

    latest_banner_summary = build_latest_banner_run_summary()

    bookmark_items = list_shared_bookmarks()
    total_bookmarks = len(bookmark_items)
    yellow_bookmarks = sum(1 for item in bookmark_items if (item.get("bookmark_level") or 0) == 1)
    deep_red_bookmarks = sum(1 for item in bookmark_items if (item.get("bookmark_level") or 0) == 2)

    recent_bookmarks = []
    for item in bookmark_items[:5]:
        copied = dict(item)
        copied["display_updated_at"] = format_display_datetime(copied.get("updated_at"))

        target_type = copied.get("target_type") or ""
        if target_type == "article":
            copied["target_type_label"] = "Article"
        elif target_type == "media":
            copied["target_type_label"] = "Media"
        elif target_type == "banner_history":
            copied["target_type_label"] = "Banner / KV"
        else:
            copied["target_type_label"] = target_type or "-"

        recent_bookmarks.append(copied)

    return render_template(
        "dashboard.html",
        page_title="Dashboard",
        latest_keyword_run=latest_keyword_run,
        latest_keyword_articles=latest_keyword_articles,
        latest_media_run=latest_media_run,
        latest_media_items=latest_media_items[:10],
        latest_banner_summary=latest_banner_summary,
        total_bookmarks=total_bookmarks,
        yellow_bookmarks=yellow_bookmarks,
        deep_red_bookmarks=deep_red_bookmarks,
        recent_bookmarks=recent_bookmarks,
    )

@app.route("/user-management")
@login_required
def user_management():
    if not admin_required():
        return redirect(url_for("dashboard"))

    users = list_users()
    return render_template(
        "user_management.html",
        page_title="User Management",
        users=users,
        success_message=None,
        error_message=None,
    )


@app.route("/user-management/create", methods=["POST"])
@login_required
def user_management_create():
    if not admin_required():
        return redirect(url_for("dashboard"))

    display_name = (request.form.get("display_name") or "").strip()
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    role = (request.form.get("role") or "user").strip()

    error_message = None
    success_message = None

    if not display_name or not username or not password:
        error_message = "이름, 아이디, 비밀번호를 모두 입력해 주세요."
    elif get_user_by_username(username):
        error_message = "이미 존재하는 아이디입니다."
    else:
        create_user(
            username=username,
            password_hash=hash_password(password),
            display_name=display_name,
            role=role if role in {"admin", "user"} else "user",
        )
        success_message = "계정이 생성되었습니다."

    users = list_users()
    return render_template(
        "user_management.html",
        page_title="User Management",
        users=users,
        success_message=success_message,
        error_message=error_message,
    )
@app.route("/user-management/delete", methods=["POST"])
@login_required
def user_management_delete():
    if not admin_required():
        return redirect(url_for("dashboard"))

    user_id_raw = (request.form.get("user_id") or "").strip()
    operation_code = (request.form.get("delete_operation_code") or "").strip()

    error_message = None
    success_message = None

    try:
        user_id = int(user_id_raw)
    except ValueError:
        user_id = None

    if not user_id:
        error_message = "삭제할 사용자 정보가 올바르지 않습니다."
    elif operation_code != INTERNAL_OPERATION_CODE:
        error_message = "운영 코드가 올바르지 않습니다."
    else:
        target_user = get_user_by_id(user_id)

        if not target_user:
            error_message = "삭제 대상 사용자를 찾을 수 없습니다."
        elif target_user.get("username") == current_username():
            error_message = "현재 로그인한 관리자 본인은 삭제할 수 없습니다."
        else:
            delete_user_by_id(user_id)
            success_message = "사용자가 삭제되었습니다."

    users = list_users()
    return render_template(
        "user_management.html",
        page_title="User Management",
        users=users,
        success_message=success_message,
        error_message=error_message,
    )

@app.route("/keyword-analysis")
@login_required
def keyword_analysis():
    latest_run = get_latest_keyword_analysis_run()
    latest_articles = []

    if latest_run:
        latest_articles = get_keyword_analysis_articles_by_run(latest_run["id"])

        for item in latest_articles:
            short_url = (item.get("short_url") or "").strip()
            article_key = short_url if short_url else f"__title__::{item.get('title') or ''}"
            item["article_key"] = article_key
            item["bookmark_level"] = get_shared_bookmark_level(f"article::{article_key}")

    return render_template(
        "keyword_analysis.html",
        page_title="Keyword Analysis",
        latest_run=latest_run,
        latest_articles=latest_articles,
    )

@app.route("/keyword-rule")
@login_required
def keyword_rule():
    forbidden_rules = list_keyword_rules("forbidden")
    required_rules = list_keyword_rules("required")

    return render_template(
        "keyword_rule.html",
        page_title="Keyword Rule",
        forbidden_rules=forbidden_rules,
        required_rules=required_rules,
    )


@app.route("/history")
@login_required
def history():
    recent_runs_raw = get_recent_keyword_analysis_runs(limit=50)
    recent_articles_raw = get_recent_keyword_analysis_articles(limit=1000)

    history_context = build_history_page_context(
        recent_runs=recent_runs_raw,
        recent_articles=recent_articles_raw,
    )

    return render_template(
        "history.html",
        page_title="History",
        recent_runs=history_context["recent_runs"],
        latest_articles=history_context["latest_articles"],
        run_articles_map=history_context["run_articles_map"],
        article_history_map=history_context["article_history_map"],
    )

@app.route("/bookmarks")
@login_required
def bookmarks():
    level_raw = (request.args.get("level") or "").strip()
    target_type = (request.args.get("target_type") or "").strip()
    keyword = (request.args.get("keyword") or "").strip().lower()

    level = None
    if level_raw in {"1", "2"}:
        level = int(level_raw)

    if target_type not in {"", "article", "media", "banner_history"}:
        target_type = ""

    bookmark_items = list_shared_bookmarks(
        bookmark_level=level,
        target_type=target_type or None,
    )

    filtered_items = []
    for idx, item in enumerate(bookmark_items, start=1):
        item["no"] = idx
        item["display_updated_at"] = format_display_datetime(item.get("updated_at"))

        item_target_type = item.get("target_type") or "-"
        item_title = item.get("title") or "-"
        item_short_url = item.get("short_url") or "-"
        item_note = item.get("note") or "-"
        item_extra = item.get("extra") or {}

        if item_target_type == "article":
            item["target_type_label"] = "Article"
            item["origin_label"] = "Keyword Article"
            item["open_url"] = item_short_url if item_short_url != "-" else ""
        elif item_target_type == "media":
            item["target_type_label"] = "Media"
            item["origin_label"] = item_extra.get("filename") or "Media Item"
            item["open_url"] = item_extra.get("media_url") or item_short_url if item_short_url != "-" else ""
        elif item_target_type == "banner_history":
            item["target_type_label"] = "Banner / KV"
            item["origin_label"] = "History Snapshot"
            item["open_url"] = ""
        else:
            item["target_type_label"] = item_target_type
            item["origin_label"] = "-"
            item["open_url"] = ""

        search_blob = " ".join([
            str(item_title),
            str(item_short_url),
            str(item_note),
            str(item["target_type_label"]),
            str(item["origin_label"]),
        ]).lower()

        if keyword and keyword not in search_blob:
            continue

        filtered_items.append(item)

    for idx, item in enumerate(filtered_items, start=1):
        item["no"] = idx

    return render_template(
        "bookmarks.html",
        page_title="Bookmarks",
        bookmark_items=filtered_items,
        current_level=level_raw,
        current_target_type=target_type,
        current_keyword=request.args.get("keyword", ""),
    )


@app.route("/api/shared-bookmarks/get", methods=["GET"])
@login_required
def api_get_shared_bookmark():
    target_key = (request.args.get("target_key") or "").strip()

    if not target_key:
        return jsonify({"error": "target_key가 필요합니다."}), 400

    bookmark = get_shared_bookmark(target_key) or {}

    return jsonify({
        "ok": True,
        "bookmark": {
            "target_key": target_key,
            "bookmark_level": bookmark.get("bookmark_level", 0) or 0,
            "note": bookmark.get("note", "") or "",
            "target_type": bookmark.get("target_type", "") or "",
            "title": bookmark.get("title", "") or "",
            "short_url": bookmark.get("short_url", "") or "",
        }
    })



@app.route("/api/bookmarks/detail", methods=["GET"])
@login_required
def api_bookmark_detail():
    target_key = (request.args.get("target_key") or "").strip()

    if not target_key:
        return jsonify({"error": "target_key가 필요합니다."}), 400

    bookmark = get_shared_bookmark(target_key)
    if not bookmark:
        return jsonify({"error": "북마크 정보를 찾을 수 없습니다."}), 404

    target_type = bookmark.get("target_type") or ""

    if target_type == "article":
        recent_articles = get_recent_keyword_analysis_articles(limit=1000)

        matched = None
        for item in recent_articles:
            short_url = (item.get("short_url") or "").strip()
            article_key = short_url if short_url else f"__title__::{item.get('title') or ''}"
            if target_key == f"article::{article_key}":
                matched = dict(item)
                break

        return jsonify({
            "ok": True,
            "target_type": "article",
            "bookmark": bookmark,
            "detail": matched,
        })

    if target_type == "media":
        recent_media_items = get_recent_media_analysis_items(limit=1000)

        matched = None
        for item in recent_media_items:
            media_target_key = f"media::{item.get('id')}"
            if media_target_key == target_key:
                matched = dict(item)
                break

        return jsonify({
            "ok": True,
            "target_type": "media",
            "bookmark": bookmark,
            "detail": matched,
        })

    if target_type == "banner_history":
        snapshot_id = None
        try:
            if "::" in target_key:
                snapshot_id = int(target_key.split("::", 1)[1])
        except Exception:
            snapshot_id = None

        detail = get_banner_monitor_snapshot_by_id(snapshot_id) if snapshot_id else None

        return jsonify({
            "ok": True,
            "target_type": "banner_history",
            "bookmark": bookmark,
            "detail": detail,
        })

    return jsonify({"error": "지원하지 않는 target_type입니다."}), 400



@app.route("/api/shared-bookmarks/save", methods=["POST"])
@login_required
def api_save_shared_bookmark():
    data = request.get_json(silent=True) or {}

    target_type = (data.get("target_type") or "").strip()
    target_key = (data.get("target_key") or "").strip()
    title = (data.get("title") or "").strip()
    short_url = (data.get("short_url") or "").strip()
    note = (data.get("note") or "").strip()
    bookmark_level = data.get("bookmark_level")
    extra = data.get("extra") or {}

    if target_type not in {"article", "media", "banner_history"}:
        return jsonify({"error": "target_type이 올바르지 않습니다."}), 400

    if not target_key:
        return jsonify({"error": "target_key가 필요합니다."}), 400

    try:
        bookmark_level = int(bookmark_level)
    except Exception:
        return jsonify({"error": "bookmark_level이 올바르지 않습니다."}), 400

    if bookmark_level not in {0, 1, 2}:
        return jsonify({"error": "bookmark_level이 올바르지 않습니다."}), 400

    saved_level = save_shared_bookmark(
        target_type=target_type,
        target_key=target_key,
        title=title,
        short_url=short_url,
        bookmark_level=bookmark_level,
        note=note,
        extra=extra,
        updated_by=current_username(),
    )

    return jsonify({
        "ok": True,
        "bookmark_level": saved_level,
    })

@app.route("/api/bookmarks/toggle", methods=["POST"])
@login_required
def api_toggle_bookmark():
    data = request.get_json(silent=True) or {}

    article_key = (data.get("article_key") or "").strip()
    short_url = (data.get("short_url") or "").strip()
    title = (data.get("title") or "").strip()

    if not article_key:
        return jsonify({"error": "article_key가 필요합니다."}), 400

    next_level = cycle_bookmark_level(
        article_key=article_key,
        short_url=short_url,
        title=title,
        updated_by=current_username(),
    )

    return jsonify({
        "ok": True,
        "bookmark_level": next_level,
    })




@app.route("/image-sizes")
@login_required
def image_sizes():
    latest_run = get_latest_media_analysis_run()
    latest_items = []

    if latest_run:
        latest_items = get_media_analysis_items_by_run(latest_run["id"])

        for item in latest_items:
            media_target_key = f"media::{item.get('id')}"
            bookmark = get_shared_bookmark(media_target_key) or {}

            item["media_target_key"] = media_target_key
            item["bookmark_level"] = bookmark.get("bookmark_level", 0) or 0
            item["bookmark_note"] = bookmark.get("note", "") or ""

    media_page_context = build_media_page_context(latest_run, latest_items)

    return render_template(
        "image_sizes.html",
        page_title="Image Size Analysis",
        latest_run=latest_run,
        latest_items=latest_items,
        media_summary_boxes=media_page_context["summary_boxes"],
        grouped_media_articles=media_page_context["grouped_articles"],
        media_heatmap_groups=media_page_context["media_heatmap_groups"],
        media_type_counts=media_page_context["media_type_counts"],
    )

@app.route("/banner-monitor")
@login_required
def banner_monitor():
    latest_run = get_latest_banner_monitor_run()
    latest_snapshots = []

    if latest_run:
        latest_snapshots = get_banner_monitor_snapshots_by_run(latest_run["id"])

    monitor_status_map = build_monitor_status_map()
    latest_run_summary = build_latest_banner_run_summary()

    return render_template(
        "banner_monitor.html",
        page_title="Banner / KV Screening",
        latest_run=latest_run,
        latest_snapshots=latest_snapshots,
        monitor_targets=MONITOR_TARGETS,
        monitor_status_map=monitor_status_map,
        latest_run_summary=latest_run_summary,
    )


@app.route("/api/keyword-rules", methods=["POST"])
@login_required
def api_create_keyword_rule():
    data = request.get_json(silent=True) or {}

    rule_type = (data.get("rule_type") or "").strip()
    keyword = (data.get("keyword") or "").strip()
    match_rule = (data.get("match_rule") or "").strip()

    allowed_rule_types = {"forbidden", "required"}
    allowed_match_rules = {
        "case_insensitive",
        "exact",
        "all_upper",
        "all_lower",
        "initial_cap",
    }

    if rule_type not in allowed_rule_types:
        return jsonify({"error": "rule_type이 올바르지 않습니다."}), 400
    if not keyword:
        return jsonify({"error": "키워드를 입력해 주세요."}), 400
    if match_rule not in allowed_match_rules:
        return jsonify({"error": "match_rule이 올바르지 않습니다."}), 400

    create_keyword_rule(rule_type, keyword, match_rule, current_username())

    return jsonify({
        "ok": True,
        "forbidden_rules": list_keyword_rules("forbidden"),
        "required_rules": list_keyword_rules("required"),
    })


@app.route("/api/keyword-rules/<int:rule_id>", methods=["DELETE"])
@login_required
def api_delete_keyword_rule(rule_id: int):
    delete_keyword_rule(rule_id)
    return jsonify({
        "ok": True,
        "forbidden_rules": list_keyword_rules("forbidden"),
        "required_rules": list_keyword_rules("required"),
    })


@app.route("/api/keyword-rules/<int:rule_id>/toggle", methods=["POST"])
@login_required
def api_toggle_keyword_rule(rule_id: int):
    data = request.get_json(silent=True) or {}
    is_active = bool(data.get("is_active"))

    update_keyword_rule_active(rule_id, is_active, current_username())

    return jsonify({
        "ok": True,
        "forbidden_rules": list_keyword_rules("forbidden"),
        "required_rules": list_keyword_rules("required"),
    })


@app.route("/api/keyword-analysis/run", methods=["POST"])
@login_required
def api_keyword_analysis_run():
    data = request.get_json(silent=True) or {}
    input_text = (data.get("input_text") or "").strip()

    if not input_text:
        return jsonify({"error": "short link를 입력해 주세요."}), 400

    forbidden_rules = get_active_keyword_rules("forbidden")
    required_rules = get_active_keyword_rules("required")

    summary, results = analyze_shortlink_batch(
        input_text=input_text,
        forbidden_rules=forbidden_rules,
        required_rules=required_rules,
    )

    run_id = create_keyword_analysis_run(
        input_text=input_text,
        input_count=summary["input_count"],
        total_links=summary["total_links"],
        total_articles=summary["total_articles"],
        flagged_articles=summary["flagged_articles"],
        missing_required_articles=summary["missing_required_articles"],
        error_articles=summary["error_articles"],
        created_by=current_username(),
    )

    for item in results:
        create_keyword_analysis_article(
            run_id=run_id,
            short_url=item.get("short_url"),
            long_url=item.get("long_url"),
            title=item.get("title"),
            published_at_raw=item.get("published_at_raw"),
            published_at_normalized=item.get("published_at_normalized"),
            body_text=item.get("body_text"),
            tags=item.get("tags", []),
            categories=item.get("categories", []),
            captions=item.get("captions", []),
            forbidden_findings=item.get("forbidden_findings", []),
            required_missing=item.get("required_missing", []),
            forbidden_found_count=item.get("forbidden_found_count", 0),
            required_missing_count=item.get("required_missing_count", 0),
            status=item.get("status", "clean"),
            error=item.get("error"),
            created_by=current_username(),
        )

    return jsonify({"ok": True, "run_id": run_id, "summary": summary, "results": results})


@app.route("/api/media-analysis/run", methods=["POST"])
@login_required
def api_media_analysis_run():
    data = request.get_json(silent=True) or {}
    input_text = (data.get("input_text") or "").strip()

    if not input_text:
        return jsonify({"error": "short link를 입력해 주세요."}), 400

    summary, results = analyze_media_shortlink_batch(input_text=input_text)

    run_id = create_media_analysis_run(
        input_text=input_text,
        total_links=summary["total_links"],
        total_media_count=summary["total_media_count"],
        error_count=summary["error_count"],
        created_by=current_username(),
    )

    for item in results:
        create_media_analysis_item(
            run_id=run_id,
            short_url=item.get("short_url"),
            long_url=item.get("long_url"),
            article_title=item.get("article_title"),
            media_url=item.get("media_url"),
            media_type=item.get("media_type"),
            filename=item.get("filename"),
            width=item.get("width"),
            height=item.get("height"),
            size_bytes=item.get("size_bytes"),
            size_display=item.get("size_display"),
            preview_url=item.get("preview_url"),
            error=item.get("error"),
            created_by=current_username(),
        )

    return jsonify({"ok": True, "run_id": run_id, "summary": summary, "results": results})


def run_banner_monitor_for_targets(targets: list[dict], run_type: str, scope_label: str | None):
    results = []
    completed_targets = 0
    error_targets = 0

    for target in targets:
        try:
            analyzed = analyze_banner_monitor_target(target)
            results.append(analyzed)
            completed_targets += 1
        except Exception:
            error_targets += 1
            results.append({
                "region": target["region"],
                "country": target["country"],
                "code": target["code"],
                "url_code": target["url_code"],
                "page_url": target["page_url"],
                "generation": target["generation"],
                "page_title": "",
                "kv_items": [],
                "banner_items": [],
            })

    run_id = create_banner_monitor_run(
        run_type=run_type,
        target_code=scope_label,
        total_targets=len(targets),
        completed_targets=completed_targets,
        error_targets=error_targets,
        created_by=current_username(),
    )

    for item in results:
        kv_items = item.get("kv_items", [])
        banner_items = item.get("banner_items", [])

        if run_type in ("scan_all_banner", "scan_filtered_banner", "scan_one_banner"):
            kv_items = []
        if run_type in ("scan_all_kv", "scan_filtered_kv", "scan_one_kv"):
            banner_items = []

        create_banner_monitor_snapshot(
            run_id=run_id,
            region=item["region"],
            country=item["country"],
            code=item["code"],
            url_code=item["url_code"],
            page_url=item["page_url"],
            generation=item["generation"],
            page_title=item.get("page_title", ""),
            kv_items=kv_items,
            banner_items=banner_items,
            created_by=current_username(),
        )

    return run_id


@app.route("/api/banner-monitor/run-all", methods=["POST"])
@login_required
def api_banner_monitor_run_all():
    data = request.get_json(silent=True) or {}
    mode = (data.get("mode") or "all").strip()

    run_type_map = {
        "all": "scan_all",
        "banner": "scan_all_banner",
        "kv": "scan_all_kv",
    }
    if mode not in run_type_map:
        return jsonify({"error": "mode가 올바르지 않습니다."}), 400

    run_banner_monitor_for_targets(
        targets=MONITOR_TARGETS,
        run_type=run_type_map[mode],
        scope_label="전체 국가",
    )
    return jsonify({"ok": True})


@app.route("/api/banner-monitor/run-filtered", methods=["POST"])
@login_required
def api_banner_monitor_run_filtered():
    data = request.get_json(silent=True) or {}
    mode = (data.get("mode") or "").strip()
    target_codes = data.get("target_codes") or []
    scope_label = (data.get("scope_label") or "현재 필터 대상").strip()

    if mode not in {"banner", "kv"}:
        return jsonify({"error": "mode가 올바르지 않습니다."}), 400
    if not target_codes:
        return jsonify({"error": "target_codes가 없습니다."}), 400

    selected_targets = []
    for code in target_codes:
        target = find_monitor_target_by_code(str(code))
        if target:
            selected_targets.append(target)

    if not selected_targets:
        return jsonify({"error": "선택된 국가를 찾을 수 없습니다."}), 400

    run_type = "scan_filtered_banner" if mode == "banner" else "scan_filtered_kv"

    run_banner_monitor_for_targets(
        targets=selected_targets,
        run_type=run_type,
        scope_label=scope_label,
    )
    return jsonify({"ok": True})


@app.route("/api/banner-monitor/run-one", methods=["POST"])
@login_required
def api_banner_monitor_run_one():
    data = request.get_json(silent=True) or {}
    target_code = (data.get("target_code") or "").strip()
    mode = (data.get("mode") or "").strip()

    if not target_code:
        return jsonify({"error": "target_code가 필요합니다."}), 400
    if mode not in {"banner", "kv"}:
        return jsonify({"error": "mode가 올바르지 않습니다."}), 400

    target = find_monitor_target_by_code(target_code)
    if not target:
        return jsonify({"error": "해당 국가 타겟을 찾을 수 없습니다."}), 404

    run_type = "scan_one_banner" if mode == "banner" else "scan_one_kv"

    run_banner_monitor_for_targets(
        targets=[target],
        run_type=run_type,
        scope_label=target_code,
    )
    return jsonify({"ok": True})


@app.route("/api/banner-monitor/history/<code>", methods=["GET"])
@login_required
def api_banner_monitor_history(code: str):
    history = get_banner_monitor_snapshots_by_code(code, limit=20)

    payload = []
    for idx, snap in enumerate(history):
        run_type = snap.get("run_type", "")

        previous_kv = None
        previous_banner = None

        if run_type in ("scan_all", "scan_all_kv", "scan_filtered_kv", "scan_one_kv", "scan_one_all") and snapshot_has_kv(snap):
            previous_kv = find_previous_snapshot_with_kv(history, idx)

        if run_type in ("scan_all", "scan_all_banner", "scan_filtered_banner", "scan_one_banner", "scan_one_all") and snapshot_has_banner(snap):
            previous_banner = find_previous_snapshot_with_banner(history, idx)

        kv_compare_summary = {"changed": False, "changed_count": 0}
        banner_compare_summary = {"changed": False, "changed_count": 0}

        if previous_kv and snapshot_has_kv(snap):
            kv_compare = compare_slot_items(previous_kv["kv_items"], snap["kv_items"])
            kv_compare_summary = {
                "changed": kv_compare["changed"],
                "changed_count": kv_compare["changed_count"],
            }

        if previous_banner and snapshot_has_banner(snap):
            banner_compare = compare_slot_items(previous_banner["banner_items"], snap["banner_items"])
            banner_compare_summary = {
                "changed": banner_compare["changed"],
                "changed_count": banner_compare["changed_count"],
            }

        bookmark = get_shared_bookmark(f"banner_history::{snap['id']}") or {}

        payload.append({
            "id": snap["id"],
            "region": snap["region"],
            "country": snap["country"],
            "code": snap["code"],
            "url_code": snap["url_code"],
            "page_url": snap["page_url"],
            "generation": snap["generation"],
            "page_title": snap["page_title"],
            "created_at": format_display_datetime(snap["created_at"]),
            "run_type": run_type,
            "kv_items": snap["kv_items"],
            "banner_items": snap["banner_items"],
            "previous_kv_items": previous_kv["kv_items"] if previous_kv else [],
            "previous_banner_items": previous_banner["banner_items"] if previous_banner else [],
            "previous_kv_created_at": format_display_datetime(previous_kv["created_at"]) if previous_kv else "-",
            "previous_banner_created_at": format_display_datetime(previous_banner["created_at"]) if previous_banner else "-",
            "kv_count": snap["kv_count"],
            "banner_count": snap["banner_count"],
            "kv_compare_summary": kv_compare_summary,
            "banner_compare_summary": banner_compare_summary,
            "bookmark_target_key": f"banner_history::{snap['id']}",
            "bookmark_level": bookmark.get("bookmark_level", 0) or 0,
            "bookmark_note": bookmark.get("note", "") or "",
        })

    return jsonify({"ok": True, "code": code, "history": payload})

if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=5000)