from fastapi import APIRouter, HTTPException, WebSocket
from datetime import datetime
import json
import asyncio

from models import (
    VideoRequest, VideoResponse, LanguagesResponse, 
    LanguageInfo, HealthResponse, RootResponse
)
from settings import  WATCH_URL
from ConnectionManager import manager
from transcripts import TranscriptListFetcher
# Create router instance
router = APIRouter()

@router.get("/", response_model=RootResponse)
async def root():
    return RootResponse(
        message="Textract API is running!",
        status="active",
        version="1.0.0",
        timestamp=datetime.now().isoformat()
    )

@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.now().isoformat()
    )


@router.post("/api/process-video", response_model=VideoResponse)
async def process_video(request: VideoRequest):
    # Simple URL validation
    if "youtube.com" not in request.video_url and "youtu.be" not in request.video_url:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
        
    # Get real video info
    video_info = await TranscriptListFetcher.get_video_info(request.video_url)
    
    if not video_info:
        raise HTTPException(status_code=404, detail="Video not found or unavailable")

    return VideoResponse(
        video_id=video_info["id"],
        title=video_info["title"],
        status="processing",
        message="Video processing started successfully"
    )

@router.get("/api/languages", response_model=LanguagesResponse)
async def get_languages():
    languages = [
        LanguageInfo(code="en", name="English", native="English"),
        LanguageInfo(code="tr", name="Turkish", native="Türkçe"),
        LanguageInfo(code="az", name="Azerbaijani", native="Azərbaycanca"),
        LanguageInfo(code="ru", name="Russian", native="Русский"),
        LanguageInfo(code="ar", name="Arabic", native="العربية"),
        LanguageInfo(code="es", name="Spanish", native="Español"),
        LanguageInfo(code="fr", name="French", native="Français"),
        LanguageInfo(code="de", name="German", native="Deutsch")
    ]
    
    return LanguagesResponse(languages=languages)

@router.websocket("/ws/transcription/{video_id}")
async def websocket_transcription(websocket: WebSocket, video_id: str):
    await manager.connect(websocket)
    try:
        # Video processing başlandığını bildir
        await manager.send_personal_message(
            json.dumps({
                "type": "status",
                "message": f"Starting live transcription for video: {video_id}",
                "video_id": video_id,
                "timestamp": datetime.now().isoformat()
            }), websocket
        )

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("action") == "start_transcription":
                print(f"Starting transcription for video: {video_id}")
                try:
                    # REAL transcript data stream
                    await TranscriptListFetcher.extract_captions_json(websocket, video_id)
                except Exception as e:
                    print(f"Transcript fetch error: {e}")
            else:
                await manager.handle_message(websocket, message)

    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        manager.disconnect(websocket)