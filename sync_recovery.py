import datetime
import os
import sys
from garminconnect import Garmin

# ==========================================
# CẤU HÌNH THÔNG TIN TÀI KHOẢN
# ==========================================
GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")

def main():
    # Xác định ngày hôm nay theo định dạng YYYY-MM-DD
    today = datetime.date.today().isoformat()
    
    try:
        print("Đang khởi tạo kết nối tới Garmin Connect...")
        client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
        client.login()
        print("Đăng nhập thành công!")

        # 1. Lấy thông tin cơ bản & nhịp tim nghỉ ngơi (RHR)
        print("- Đang tải chỉ số sinh học cơ bản...")
        stats = client.get_stats(today)
        resting_hr = stats.get('restingHeartRate', 'N/A')
        steps = stats.get('totalSteps', 'N/A')

        # 2. Lấy chỉ số Biến thiên nhịp tim (HRV) qua đêm
        print("- Đang tải chỉ số HRV...")
        try:
            hrv_data = client.get_hrv_data(today)
            hrv_summary = hrv_data.get('hrvSummary', {})
            hrv_val = hrv_summary.get('lastNightAvg', 'N/A')
        except Exception:
            hrv_val = "N/A (Chưa đeo đồng hồ khi ngủ)"

        # 3. Lấy dữ liệu Giấc ngủ (Thời gian & Điểm số)
        print("- Đang tải dữ liệu giấc ngủ...")
        try:
            sleep_data = client.get_sleep_data(today)
            sleep_dto = sleep_data.get('dailySleepDTO', {})
            sleep_seconds = sleep_dto.get('sleepTimeSeconds', 0)
            sleep_duration = round(sleep_seconds / 3600, 1) if sleep_seconds else 'N/A'
            sleep_score = sleep_dto.get('sleepScore', 'N/A')
        except Exception:
            sleep_duration, sleep_score = 'N/A', 'N/A'

        # 4. Lấy dữ liệu Body Battery (Năng lượng cơ thể)
        print("- Đang tải dữ liệu Body Battery...")
        try:
            bb_data = client.get_body_battery(today)
            # Tìm giá trị nạp/xả lớn nhất và nhỏ nhất trong ngày
            bb_values = [item.get('value') for item in bb_data if item.get('value') is not None]
            bb_str = f"{min(bb_values)} -> {max(bb_values)}" if bb_values else "N/A"
        except Exception:
            bb_str = "N/A"

        # 5. Lấy điểm Sẵn sàng tập luyện (Training Readiness)
        print("- Đang tải trạng thái sẵn sàng tập luyện...")
        try:
            readiness_data = client.get_training_readiness(today)
            # Thư viện trả về danh sách hoặc object tùy phiên bản, lấy score gần nhất
            if isinstance(readiness_data, list) and len(readiness_data) > 0:
                readiness_score = readiness_data[-1].get('score', 'N/A')
            else:
                readiness_score = readiness_data.get('trainingReadinessScore', 'N/A')
        except Exception:
            readiness_score = "N/A"

        # ==========================================
        # XUẤT DỮ LIỆU RA FILE MARKDOWN (.md)
        # ==========================================
        # Tạo thư mục lưu trữ nếu chưa tồn tại
        output_dir = "garmin_daily"
        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"{today}.md")

        markdown_template = f"""# Chỉ số phục hồi Garmin - {today}

## Sức khỏe & Tải tập luyện
- **Nhịp tim lúc nghỉ (Resting HR):** {resting_hr} bpm
- **Biến thiên nhịp tim (HRV qua đêm):** {hrv_val} ms
- **Giấc ngủ:** {sleep_duration} giờ (Điểm số chất lượng: {sleep_score})
- **Body Battery (Thấp nhất -> Cao nhất):** {bb_str}
- **Mức độ sẵn sàng tập luyện (Training Readiness):** {readiness_score}
- **Vận động cơ bản (Số bước chân):** {steps} bước

---
*Dữ liệu được đồng bộ hóa tự động vào lúc {datetime.datetime.now().strftime('%H:%M:%S')}*
"""

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(markdown_template)

        print(f"\n[THÀNH CÔNG] Đã ghi nhận dữ liệu thể trạng vào file: {file_path}")

    except Exception as e:
        print(f"\n[LỖI HỆ THỐNG] Không thể kết nối hoặc lấy dữ liệu: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # ==========================================
        # ĐẨY DỮ LIỆU LÊN GOOGLE SHEETS
        # ==========================================
        webapp_url = os.getenv("WEBAPP_URL")
        
        if webapp_url:
            import requests
            
            # Đóng gói dữ liệu thành JSON
            payload = {
                "date": today,
                "rhr": resting_hr,
                "hrv": hrv_val,
                "sleep_hours": sleep_duration,
                "sleep_score": sleep_score,
                "body_battery": bb_str,
                "readiness": readiness_score,
                "steps": steps
            }
            
            print("- Đang gửi dữ liệu lên Google Sheets...")
            response = requests.post(webapp_url, json=payload)
            
            if response.status_code == 200:
                print(f"[THÀNH CÔNG] Đã cập nhật dòng dữ liệu mới vào Google Sheets.")
            else:
                print(f"[LỖI] Phản hồi từ server: {response.text}")
    main()
