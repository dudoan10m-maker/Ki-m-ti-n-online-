# Đào Vàng Backend (starter)

Backend Flask + SQLAlchemy; dùng PostgreSQL qua `DATABASE_URL` để dữ liệu bền vững trên Render. SQLite chỉ phù hợp chạy thử cục bộ.

## Deploy trên Render
1. Đưa `app.py`, `requirements.txt`, `render.yaml` lên GitHub.
2. Tạo PostgreSQL database trên Render; sao chép Internal Database URL vào biến `DATABASE_URL` của web service.
3. Đặt `ADMIN_TOKEN` thành một chuỗi ngẫu nhiên dài, bí mật trong Environment. Không đưa token vào HTML công khai.
4. Đặt `ALLOWED_ORIGINS` thành origin website game, ví dụ `https://TEN-WEBSITE.netlify.app` (không có dấu `/` cuối).
5. Deploy; kiểm tra `https://TEN-BACKEND.onrender.com/health`.

## API
- `GET /health`
- `POST /api/player/init` JSON `{"player_id":"mã-người-chơi"}`
- `GET /api/player/<player_id>`
- `POST /api/player/<player_id>/withdrawals` JSON:
  `{"bank":"Tên ngân hàng","account_number":"...","account_owner":"...","amount_vnd":10000,"xu_deducted":1000}`
- `GET /api/admin/withdrawals` header `Authorization: Bearer <ADMIN_TOKEN>`
- `POST /api/admin/withdrawals/<id>/decision` header trên, JSON `{"decision":"mark_paid","note":"Đã đối soát thủ công"}` hoặc `{"decision":"reject","note":"Lý do"}`

## Giới hạn quan trọng
- Đây là backend khung để lưu yêu cầu, KHÔNG tự chuyển khoản.
- API hiện không có cơ chế kiếm xu đáng tin cậy. Không được mở rút tiền thật cho tới khi số dư được ghi nhận/đối soát hoàn toàn ở máy chủ; không tin điểm/xu do trình duyệt gửi lên.
- `mark_paid` chỉ đánh dấu thủ công, không chuyển tiền.
- Admin token phải chỉ nằm ở môi trường server, không nhúng vào JavaScript frontend.
- Thông tin ngân hàng là dữ liệu nhạy cảm: chỉ thu thập khi cần, giới hạn quyền truy cập và cân nhắc yêu cầu phụ huynh/người giám hộ hỗ trợ.
