import logging
import httpx
from typing import Dict, Any, Optional, List
from app.config import settings

logger = logging.getLogger(__name__)

class WhatsAppClient:
    @property
    def token(self) -> str:
        return (settings.WHATSAPP_TOKEN or "").strip()

    @property
    def phone_number_id(self) -> str:
        return (settings.WHATSAPP_PHONE_NUMBER_ID or "").strip()

    @property
    def api_url(self) -> str:
        return f"{settings.WHATSAPP_API_URL}/{self.phone_number_id}/messages" if self.phone_number_id else ""

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def is_configured(self) -> bool:
        return bool(self.token and self.phone_number_id)

    async def send_text_message(self, recipient_phone: str, text: str) -> Dict[str, Any]:
        """Send a standard text message via WhatsApp Cloud API."""
        clean_recipient = recipient_phone.strip().replace("+", "")
        if not self.is_configured():
            logger.warning(
                f"[MOCK WHATSAPP SEND to {clean_recipient}]: {text[:100]}... "
                "(Note: WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID is not configured in Railway variables!)"
            )
            return {"status": "mocked", "recipient": clean_recipient, "text": text}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_recipient,
            "type": "text",
            "text": {"preview_url": True, "body": text}
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.api_url, json=payload, headers=self.headers, timeout=10.0)
                res_data = response.json()
                if response.status_code != 200:
                    logger.error(f"❌ Meta WhatsApp API Error ({response.status_code}) for {clean_recipient}: {res_data}")
                else:
                    logger.info(f"✅ WhatsApp message successfully dispatched via Meta Cloud API to {clean_recipient}")
                return res_data
        except Exception as e:
            logger.error(f"❌ Failed to send WhatsApp message to {clean_recipient}: {e}")
            return {"error": str(e)}

    async def send_interactive_buttons(
        self, recipient_phone: str, body_text: str, buttons: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Send interactive quick reply buttons via WhatsApp Cloud API.
        buttons format: [{"id": "btn_1", "title": "Option 1"}, ...] (max 3 buttons)
        """
        if not self.is_configured():
            button_titles = ", ".join([b.get("title", "") for b in buttons])
            logger.info(f"[MOCK WHATSAPP BUTTONS to {recipient_phone}]: {body_text} (Buttons: {button_titles})")
            return {"status": "mocked", "recipient": recipient_phone, "text": body_text}

        action_buttons = []
        for btn in buttons[:3]:
            action_buttons.append({
                "type": "reply",
                "reply": {
                    "id": btn.get("id", f"btn_{btn.get('title')}"),
                    "title": btn.get("title", "")[:20]  # Max 20 chars
                }
            })

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {"buttons": action_buttons}
            }
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.api_url, json=payload, headers=self.headers, timeout=10.0)
                return response.json()
        except Exception as e:
            logger.error(f"Failed to send WhatsApp interactive buttons: {e}")
            return {"error": str(e)}

    async def mark_message_as_read(self, message_id: str) -> bool:
        """Mark an incoming WhatsApp message as read."""
        if not self.is_configured():
            return True

        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id
        }
        try:
            async with httpx.AsyncClient() as client:
                await client.post(self.api_url, json=payload, headers=self.headers, timeout=5.0)
            return True
        except Exception:
            return False

    async def download_media(self, media_id: str) -> Optional[bytes]:
        """Retrieve binary content for voice notes or images from WhatsApp Graph API."""
        if not self.token or not media_id:
            return None

        try:
            async with httpx.AsyncClient() as client:
                # Step 1: Get media URL
                media_info_url = f"{settings.WHATSAPP_API_URL}/{media_id}"
                res = await client.get(media_info_url, headers=self.headers, timeout=10.0)
                if res.status_code != 200:
                    return None
                download_url = res.json().get("url")
                if not download_url:
                    return None

                # Step 2: Download binary data
                media_res = await client.get(download_url, headers=self.headers, timeout=15.0)
                if media_res.status_code == 200:
                    return media_res.content
                return None
        except Exception as e:
            logger.error(f"Error downloading WhatsApp media {media_id}: {e}")
            return None

whatsapp_client = WhatsAppClient()
