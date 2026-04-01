from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict

# تعريف التطبيق بتاعنا
app = FastAPI(title="RandCam Backend")

# إعدادات الـ CORS عشان نسمح للفرونت إند يتصل بالسيرفر من أي مكان
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        # هنا بنخزن اليوزر اللي دخل ومستني حد يتصل بيه
        self.waiting_user: WebSocket | None = None
        # القاموس ده بيسجل كل يوزر ومين الشخص اللي بيكلمه (الـ Partner)
        self.active_connections: Dict[WebSocket, WebSocket] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        
        # لو مفيش حد مستني في الطابور، حط اليوزر ده في الانتظار
        if self.waiting_user is None:
            self.waiting_user = websocket
            await websocket.send_json({"type": "status", "message": "مستنيين حد يدخل..."})
        else:
            # لو فيه حد مستني، اربطهم ببعض فوراً
            partner = self.waiting_user
            
            # سجل كل واحد مين الـ Partner بتاعه
            self.active_connections[websocket] = partner
            self.active_connections[partner] = websocket
            
            # فضي مكان الانتظار عشان الناس الجديدة اللي هتدخل
            self.waiting_user = None
            
            # بلغ الاتنين إنهم اتوصلوا ببعض
            await websocket.send_json({"type": "status", "message": "لقينا حد! جاري الاتصال..."})
            await partner.send_json({"type": "status", "message": "لقينا حد! جاري الاتصال..."})
            
            # ادي إشارة لواحد فيهم إنه يبدأ يبعت بيانات الكاميرا (Offer)
            await partner.send_json({"type": "init_webrtc"})

    def disconnect(self, websocket: WebSocket):
        # لو اللي قفل الصفحة كان هو اللي مستني أساساً، شيله من الانتظار
        if self.waiting_user == websocket:
            self.waiting_user = None
            return None
            
        # لو كان مرتبط بحد وبيكلمه، افصلهم وهات بيانات التاني عشان نبلغه
        if websocket in self.active_connections:
            partner = self.active_connections[websocket]
            del self.active_connections[websocket]
            del self.active_connections[partner]
            return partner
        return None

    async def send_to_partner(self, sender: WebSocket, message: dict):
        # ابعت بيانات الـ WebRTC (الصوت/الصورة) للشخص المرتبط بيك بس
        if sender in self.active_connections:
            partner = self.active_connections[sender]
            try:
                await partner.send_json(message)
            except Exception:
                pass

# خدنا نسخة من الكلاس عشان نشغله
manager = ConnectionManager()

# ده الـ Endpoint اللي المتصفح بيتصل بيه
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # استقبل أي بيانات (Offer, Answer, ICE Candidate) من المتصفح
            data = await websocket.receive_json()
            
            # مررها فوراً للـ Partner
            await manager.send_to_partner(websocket, data)
            
    except WebSocketDisconnect:
        # لو حد فيهم قفل الصفحة أو النت قطع عنده
        partner = manager.disconnect(websocket)
        if partner:
            try:
                # بلغ التاني إن الشات قفل خليه يفصل الكاميرا من عنده
                await partner.send_json({
                    "type": "peer_disconnected", 
                    "message": "الطرف التاني قفل الخط."
                })
            except:
                pass
