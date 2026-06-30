import datetime
import os
import sys
import requests
from garminconnect import Garmin

# ==========================================
# CẤU HÌNH THÔNG TIN TÀI KHOẢN
# ==========================================
GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")
WEBAPP_URL = os.getenv("WEBAPP_URL")


def safe_get(fn, *args, default="N/A", label=""):
    """Gọi 1 hàm Garmin API, nếu lỗi thì trả về default thay vì sập chương trình."""
    try:
        return fn(*args)
    except Exception as e:
        print(f"  [Cảnh báo] Không lấy được {label}: {e}")
        return default


def push_to_sheets(payload):
    if not WEBAPP_URL:
        print("- Bỏ qua đẩy lên Sheets (chưa cấu hình WEBAPP_URL).")
        return
    try:
        resp = requests.post(WEBAPP_URL, json=payload, timeout=30)
        if resp.status_code == 200:
            print(f"[THÀNH CÔNG] Đã đẩy dữ liệu loại '{payload.get('type')}' lên Google Sheets.")
        else:
            print(f"[LỖI] Server phản hồi {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[LỖI] Không gửi được lên Google Sheets: {e}")


def collect_recovery(client, today):
    print("- Đang tải chỉ số sinh học cơ bản...")
    stats = safe_get(client.get_stats, today, default={}, label="stats")
    resting_hr = stats.get("restingHeartRate", "N/A")
    steps = stats.get("totalSteps", "N/A")

    print("- Đang tải chỉ số HRV...")
    hrv_data = safe_get(client.get_hrv_data, today, default={}, label="HRV")
    hrv_val = (hrv_data or {}).get("hrvSummary", {}).get("lastNightAvg", "N/A")

    print("- Đang tải dữ liệu giấc ngủ...")
    sleep_data = safe_get(client.get_sleep_data, today, default={}, label="giấc ngủ")
    sleep_dto = (sleep_data or {}).get("dailySleepDTO", {})
    sleep_seconds = sleep_dto.get("sleepTimeSeconds", 0)
    sleep_duration = round(sleep_seconds / 3600, 1) if sleep_seconds else "N/A"
    sleep_score = sleep_dto.get("sleepScore", "N/A")

    print("- Đang tải dữ liệu Body Battery...")
    bb_data = safe_get(client.get_body_battery, today, default=[], label="Body Battery")
    bb_values = [item.get("value") for item in (bb_data or []) if item.get("value") is not None]
    bb_str = f"{min(bb_values)} -> {max(bb_values)}" if bb_values else "N/A"

    print("- Đang tải trạng thái sẵn sàng tập luyện...")
    readiness_data = safe_get(client.get_training_readiness, today, default={}, label="training readiness")
    if isinstance(readiness_data, list) and len(readiness_data) > 0:
        readiness_score = readiness_data[-1].get("score", "N/A")
    elif isinstance(readiness_data, dict):
        readiness_score = readiness_data.get("trainingReadinessScore", "N/A")
    else:
        readiness_score = "N/A"

    return {
        "type": "recovery",
        "date": today,
        "rhr": resting_hr,
        "hrv": hrv_val,
        "sleep_hours": sleep_duration,
        "sleep_score": sleep_score,
        "body_battery": bb_str,
        "readiness": readiness_score,
        "steps": steps,
    }


def collect_activities(client, days_back=7):
    """Lấy các buổi tập (chủ yếu chạy bộ) trong N ngày gần nhất."""
    print(f"- Đang tải {days_back} buổi tập gần nhất...")
    activities = safe_get(client.get_activities, 0, days_back, default=[], label="activities")

    results = []
    for act in activities or []:
        act_type = act.get("activityType", {}).get("typeKey", "unknown")
        # Chỉ lấy các loại chạy bộ (running, trail_running, treadmill_running...)
        if "running" not in act_type:
            continue

        activity_id = act.get("activityId")
        distance_km = round((act.get("distance") or 0) / 1000, 2)
        duration_min = round((act.get("duration") or 0) / 60, 1)
        avg_pace_sec_per_km = (
            round((act.get("duration") or 0) / distance_km, 0) if distance_km else None
        )
        avg_hr = act.get("averageHR", "N/A")
        max_hr = act.get("maxHR", "N/A")
        cadence = act.get("averageRunningCadenceInStepsPerMinute", "N/A")
        elevation_gain = act.get("elevationGain", "N/A")
        aerobic_te = act.get("aerobicTrainingEffect", "N/A")
        anaerobic_te = act.get("anaerobicTrainingEffect", "N/A")
        vo2max = act.get("vO2MaxValue", "N/A")
        calories = act.get("calories", "N/A")

        results.append({
            "type": "activity",
            "activity_id": activity_id,
            "date": act.get("startTimeLocal", "N/A"),
            "activity_type": act_type,
            "distance_km": distance_km,
            "duration_min": duration_min,
            "avg_pace_min_per_km": (
                f"{int(avg_pace_sec_per_km // 60)}:{int(avg_pace_sec_per_km % 60):02d}"
                if avg_pace_sec_per_km else "N/A"
            ),
            "avg_hr": avg_hr,
            "max_hr": max_hr,
            "cadence_spm": cadence,
            "elevation_gain_m": elevation_gain,
            "aerobic_te": aerobic_te,
            "anaerobic_te": anaerobic_te,
            "vo2max": vo2max,
            "calories": calories,
        })

    print(f"  Tìm thấy {len(results)} buổi chạy trong {days_back} ngày qua.")
    return results


def collect_training_status(client, today):
    print("- Đang tải Training Status & VO2max...")
    ts_data = safe_get(client.get_training_status, today, default={}, label="training status")

    vo2max_running = "N/A"
    training_status_text = "N/A"
    try:
        most_recent = list(ts_data.get("mostRecentVO2Max", {}).values())
        if most_recent:
            vo2max_running = most_recent[0].get("generic", {}).get("vo2MaxValue", "N/A")
    except Exception:
        pass
    try:
        latest_status = list(ts_data.get("mostRecentTrainingStatus", {}).get("latestTrainingStatusData", {}).values())
        if latest_status:
            training_status_text = latest_status[0].get("trainingStatusFeedbackPhrase", "N/A")
    except Exception:
        pass

    print("- Đang tải dự đoán thành tích race...")
    race_predictions = safe_get(client.get_race_predictions, default={}, label="race predictions")

    return {
        "type": "training_status",
        "date": today,
        "vo2max": vo2max_running,
        "training_status": training_status_text,
        "race_pred_5k": race_predictions.get("time5K", "N/A"),
        "race_pred_10k": race_predictions.get("time10K", "N/A"),
        "race_pred_half": race_predictions.get("timeHalfMarathon", "N/A"),
        "race_pred_full": race_predictions.get("timeMarathon", "N/A"),
    }


def write_markdown(today, recovery, activities, training_status):
    output_dir = "garmin_daily"
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{today}.md")

    activities_md = ""
    if activities:
        for a in activities:
            activities_md += (
                f"\n### {a['date']} — {a['activity_type']}\n"
                f"- Quãng đường: {a['distance_km']} km | Thời gian: {a['duration_min']} phút | "
                f"Pace TB: {a['avg_pace_min_per_km']} /km\n"
                f"- HR TB/Max: {a['avg_hr']} / {a['max_hr']} bpm | Cadence: {a['cadence_spm']} spm | "
                f"Độ cao: {a['elevation_gain_m']} m\n"
                f"- Training Effect (Aerobic/Anaerobic): {a['aerobic_te']} / {a['anaerobic_te']} | "
                f"Calories: {a['calories']}\n"
            )
    else:
        activities_md = "\n*Không có buổi chạy nào trong kỳ này.*\n"

    markdown_template = f"""# Chỉ số phục hồi & tập luyện Garmin - {today}

## Sức khỏe & Tải tập luyện
- **Nhịp tim lúc nghỉ (Resting HR):** {recovery['rhr']} bpm
- **Biến thiên nhịp tim (HRV qua đêm):** {recovery['hrv']} ms
- **Giấc ngủ:** {recovery['sleep_hours']} giờ (Điểm số chất lượng: {recovery['sleep_score']})
- **Body Battery (Thấp nhất -> Cao nhất):** {recovery['body_battery']}
- **Mức độ sẵn sàng tập luyện (Training Readiness):** {recovery['readiness']}
- **Vận động cơ bản (Số bước chân):** {recovery['steps']} bước

## VO2max & Trạng thái tập luyện
- **VO2max (chạy bộ):** {training_status['vo2max']}
- **Trạng thái tập luyện:** {training_status['training_status']}
- **Dự đoán 5K / 10K / Bán marathon / Marathon:** {training_status['race_pred_5k']} / {training_status['race_pred_10k']} / {training_status['race_pred_half']} / {training_status['race_pred_full']}

## Các buổi chạy gần đây
{activities_md}
---
*Dữ liệu được đồng bộ hóa tự động vào lúc {datetime.datetime.now().strftime('%H:%M:%S')}*
"""

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(markdown_template)

    print(f"\n[THÀNH CÔNG] Đã ghi nhận dữ liệu vào file: {file_path}")


def main():
    today = datetime.date.today().isoformat()

    print("Đang khởi tạo kết nối tới Garmin Connect...")
    try:
        client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
        client.login()
        print("Đăng nhập thành công!")
    except Exception as e:
        print(f"\n[LỖI HỆ THỐNG] Không thể đăng nhập Garmin Connect: {e}")
        sys.exit(1)

    recovery = collect_recovery(client, today)
    activities = collect_activities(client, days_back=7)
    training_status = collect_training_status(client, today)

    write_markdown(today, recovery, activities, training_status)

    # Đẩy lên Google Sheets (3 loại payload, GAS sẽ tự định tuyến theo "type")
    push_to_sheets(recovery)
    for act in activities:
        push_to_sheets(act)
    push_to_sheets(training_status)


if __name__ == "__main__":
    main()
