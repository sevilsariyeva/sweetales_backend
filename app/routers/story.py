import os
import uuid
import shutil
import base64
import logging
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from decouple import config
from .. import crud, models, schemas, auth
from ..database import get_db
import openai

# optional pydub import for slowing audio
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except Exception:
    PYDUB_AVAILABLE = False

router = APIRouter(prefix="/api", tags=["story"])

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure OpenAI API
openai.api_key = config('OPENAI_API_KEY')

UPLOAD_DIR = "uploads"
AUDIO_DIR = "audio"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

LANGUAGE_PROMPTS = {
    'en': 'English',
    'tr': 'Turkish',
    'ru': 'Russian',
    'az': 'Azerbaijani'
}

# Map our friendly voice names to OpenAI voice identifiers (adjust to your account)
VOICE_MAP = {
    "grandma": "sage",   # soft female / elderly-like
    "female": "sage",
    "girl": "verse",
    "male": "alloy",
    "boy": "copper"
}

def create_elderly_voice_audio(text: str, output_path: str, voice: str = "grandma") -> bool:
    """
    Generate audio using OpenAI TTS. Returns True if file written successfully.
    """
    try:
        selected_voice = VOICE_MAP.get(voice, voice)
        logger.info(f"TTS: using voice '{selected_voice}'")

        response = openai.audio.speech.create(
            model="tts-1",
            voice=selected_voice,
            input=text
        )

        # robustly get bytes from response
        audio_bytes = None
        if hasattr(response, "content"):
            audio_bytes = response.content
        elif isinstance(response, (bytes, bytearray)):
            audio_bytes = response
        else:
            audio_bytes = getattr(response, "audio", None) or getattr(response, "data", None)

        # some clients give dict with 'data'
        if isinstance(audio_bytes, dict) and "data" in audio_bytes:
            audio_bytes = audio_bytes["data"]

        # try response.read()
        if not audio_bytes:
            try:
                audio_bytes = response.read()
            except Exception:
                audio_bytes = None

        if not audio_bytes:
            logger.error("TTS: no audio bytes returned")
            return False

        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        ok = os.path.exists(output_path) and os.path.getsize(output_path) > 0
        if ok:
            logger.info(f"TTS: wrote audio to {output_path}")
        else:
            logger.error("TTS: file empty after write")
        return ok

    except Exception as e:
        logger.exception(f"TTS exception: {e}")
        return False

def make_slow_version(input_path: str, output_path: str, speed_factor: float = 0.7) -> bool:
    """
    Create slower audio with pydub by reducing frame_rate. Returns True on success.
    speed_factor < 1 -> slower (e.g., 0.7)
    """
    if not PYDUB_AVAILABLE:
        logger.warning("pydub not available — skipping slow audio creation")
        return False
    try:
        sound = AudioSegment.from_file(input_path)
        # slower by decreasing frame_rate, keep original frame_rate for export
        slower = sound._spawn(sound.raw_data, overrides={
            "frame_rate": int(sound.frame_rate * speed_factor)
        }).set_frame_rate(sound.frame_rate)
        slower.export(output_path, format="mp3")
        ok = os.path.exists(output_path) and os.path.getsize(output_path) > 0
        if ok:
            logger.info(f"Slow audio saved: {output_path}")
        else:
            logger.error("Slow audio creation failed (file empty)")
        return ok
    except Exception as e:
        logger.exception(f"Error creating slow audio: {e}")
        return False

@router.post("/generate-story")
async def generate_story(
    file: UploadFile = File(...),
    language: str = Form(...),
    voice: str = Form(default="grandma"),
    slow: bool = Form(default=True),  # client may pass slow=false to skip slow variant
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    logger.info(f"Request: language={language}, voice={voice}, slow={slow}, user={current_user.email}")

    # credits
    if current_user.credits < 5:
        raise HTTPException(status_code=402, detail=f"Insufficient credits. You have {current_user.credits} credits, need 5.")

    # validate image
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed")
    file_ext = file.filename.split(".")[-1].lower()
    if file_ext not in ["jpg", "jpeg", "png", "gif", "webp"]:
        raise HTTPException(status_code=400, detail="Unsupported image format")

    # save uploaded image
    file_name = f"{uuid.uuid4()}.{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, file_name)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"Saved image: {file_path}")
    except Exception as e:
        logger.exception("Saving uploaded image failed")
        raise HTTPException(status_code=500, detail=f"Error saving file: {e}")

    # build prompt (force Azerbaijani if requested)
    with open(file_path, "rb") as f:
        base64_image = base64.b64encode(f.read()).decode("utf-8")

    language_name = LANGUAGE_PROMPTS.get(language, language)
    # stricter instruction if az
    strict_az = ""
    if language == "az":
        strict_az = (
            "IMPORTANT: Write strictly in Azerbaijani. "
            "Do NOT use Turkish words or Turkish-specific spelling. "
            "Use Azerbaijani vocabulary and orthography only. "
            "Make pronunciation and stress consistent with Azerbaijani."
        )

    prompt = f"""
You are a wise, warm grandmother telling a magical bedtime story to your grandchildren.

LANGUAGE: Write the ENTIRE story in {language_name} only. Every single word must be in {language_name}.
{strict_az}

STEP 1 — OBSERVE THE IMAGE CAREFULLY:
Look at every detail in the image:
- Who or what is in it? (people, animals, objects, nature)
- What colors, textures, and shapes do you see?
- What is the setting? (indoors, outdoors, forest, city, sea, etc.)
- What mood or emotion does the image convey?
- Are there any small or hidden details?

STEP 2 — BUILD THE STORY FROM THOSE DETAILS:
Use what you actually see in the image as the foundation of the story.
- The main character(s) must come directly from the image
- The setting must match the image's environment
- Include at least 3 specific visual details from the image naturally woven into the story
- Do NOT invent a story that ignores the image — every major element must connect to it

STEP 3 — MAKE IT MAGICAL & CHILD-FRIENDLY:
- Add a sprinkle of magic or wonder (a talking animal, a glowing object, a secret door, etc.)
- Include a gentle moral lesson (kindness, bravery, sharing, honesty)
- Use vivid, sensory language — what does it smell like? sound like? feel like?
- Build suspense with a small problem or mystery, then resolve it warmly
- End with a cozy, satisfying conclusion that makes children feel safe and happy

STORY STRUCTURE:
- Beginning (~150 words): Introduce the character(s) and setting from the image
- Middle (~300 words): A challenge, adventure, or mystery tied to image details
- End (~150 words): Resolution with a warm moral message

VOICE & STYLE:
- Narrate as a loving grandmother — warm, patient, slightly poetic
- Use short paragraphs, gentle rhythm, and age-appropriate vocabulary
- Occasionally address the grandchildren directly ("And do you know what happened next, my dears?")
- Total length: 400–700 words

Write the story now in {language}:
"""   # call chat model
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/{file_ext};base64,{base64_image}", "detail": "high"}}
                    ]
                }
            ],
            max_tokens=1200,
            temperature=0.7
        )
        # robust extraction
        story = ""
        try:
            story = response.choices[0].message.content.strip()
        except Exception:
            story = getattr(response, "text", "") or str(response)

        if not story:
            raise Exception("Empty story returned")
        logger.info("Story generated")
    except Exception as e:
        logger.exception("Story generation failed")
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Error generating story: {e}")

    # generate TTS audio (original)
    tts_file_name = f"{uuid.uuid4()}.mp3"
    tts_path = os.path.join(AUDIO_DIR, tts_file_name)
    try:
        if not create_elderly_voice_audio(story, tts_path, voice=voice):
            logger.warning("Primary TTS failed, trying fallback 'sage'")
            if not create_elderly_voice_audio(story, tts_path, voice="sage"):
                raise Exception("TTS creation failed for both primary and fallback voices")
        logger.info(f"Audio created: {tts_path}")
    except Exception as e:
        logger.exception("Audio generation failed")
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Error generating audio: {e}")

    # optionally create slow variant using pydub
    slow_file_name = None
    if slow:
        if PYDUB_AVAILABLE:
            slow_file_name = tts_file_name.replace(".mp3", "_slow.mp3")
            slow_path = os.path.join(AUDIO_DIR, slow_file_name)
            ok = make_slow_version(tts_path, slow_path, speed_factor=0.7)  # ~22% slower
            if not ok:
                logger.warning("Slow variant creation failed; continuing with original only")
                slow_file_name = None
        else:
            logger.info("pydub not installed; skipping slow variant")
            slow_file_name = None

    # deduct credits
    updated_user = crud.deduct_user_credits(db, current_user.id, 5)
    if not updated_user:
        # cleanup on failure
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(tts_path):
            os.remove(tts_path)
        if slow_file_name and os.path.exists(os.path.join(AUDIO_DIR, slow_file_name)):
            os.remove(os.path.join(AUDIO_DIR, slow_file_name))
        raise HTTPException(status_code=402, detail="Failed to deduct credits")

    # prepare title
    story_lines = [ln.strip() for ln in story.split("\n") if ln.strip()]
    title = (story_lines[0][:50] + "...") if story_lines and len(story_lines[0]) > 50 else (story_lines[0] if story_lines else f"Story in {language_name}")

    # save story to DB (audio_url pointing to slow variant if exists else original)
    saved_audio_url = f"/api/audio/{slow_file_name}" if slow_file_name else f"/api/audio/{tts_file_name}"
    story_data = {
        "content": story,
        "language": language,
        "audio_url": saved_audio_url,
        "has_audio": True,
        "image_filename": file_name,
        "title": title,
        "genre": "adventure"
    }

    try:
        db_story = crud.create_story(db, story_data, current_user.id)
    except Exception as e:
        logger.exception("Saving story to DB failed")
        # attempt cleanup (but don't crash if cleanup fails)
        try:
            if os.path.exists(file_path): os.remove(file_path)
            if os.path.exists(tts_path): os.remove(tts_path)
            if slow_file_name and os.path.exists(os.path.join(AUDIO_DIR, slow_file_name)):
                os.remove(os.path.join(AUDIO_DIR, slow_file_name))
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error saving story: {e}")

    # remove uploaded image (we keep audio files)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass

    base_url = config("BASE_URL", default="http://localhost:8000")

    resp = {
        "success": True,
        "story": story,
        "story_id": db_story.id,
        "title": db_story.title,
        "audioUrl": saved_audio_url,
        "fullAudioUrl": f"{base_url}{saved_audio_url}",
        "audioFileName": slow_file_name if slow_file_name else tts_file_name,
        "originalAudioFileName": tts_file_name,
        "slowVariantCreated": bool(slow_file_name),
        "user_credits": updated_user.credits,
        "has_audio": True,
    }
    return JSONResponse(resp)


@router.get("/audio/{file_name}")
async def get_audio(file_name: str):
    # sanitization
    if ".." in file_name or "/" in file_name or "\\" in file_name:
        raise HTTPException(status_code=400, detail="Invalid file name")
    if not file_name.endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Only mp3 supported")

    file_path = os.path.join(AUDIO_DIR, file_name)
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    def iterfile(path: str, chunk_size: int = 1024 * 64):
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    file_size = os.path.getsize(file_path)
    return StreamingResponse(
        iterfile(file_path),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f"inline; filename={file_name}",
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache",
            "Content-Length": str(file_size)
        }
    )


@router.get("/my-stories", response_model=list[schemas.Story])
async def get_my_stories(current_user: models.User = Depends(auth.get_current_active_user), db: Session = Depends(get_db)):
    return crud.get_user_stories(db, current_user.id)
