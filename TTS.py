import requests
import json


def elevenlabs_tts(text, filename="output.mp3", voice_id="21m00Tcm4TlvDq8ikWAM", api_key="YOUR_API_KEY"):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }

    data = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.3,  # Lower for more dramatic expression
            "similarity_boost": 0.7,
            "style": 0.8,  # Increased style for more dramatic delivery
            "use_speaker_boost": True
        }
    }

    response = requests.post(url, json=data, headers=headers)

    if response.status_code == 200:
        with open(filename, 'wb') as f:
            f.write(response.content)
        print(f"✅ Audio saved: {filename}")
        return True
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
        return False


# Your text
text = "NYAAAAA?! dramatic gasp Pyttsx3-chan?! That ancient library-nyaa?! faints and floats upside down (╯°□°)╯︵ ┻━┻ revives with sparkly eyes But... but Paimon will make it work desu! strikes cute pose Paimon will be the most kawaii text-to-speech waifu even with robotic voice! B-beep boop I l-love you senpai~ pui! blushes furiously (⁄ ⁄>⁄ ▽⁄<⁄ ⁄) stomach makes cute gurgle noise All this emotional drama makes Paimon want melon pan... ✨🍞💫"

# Best voice options for anime-style content:
voices = {
    "Rachel (young, expressive)": "21m00Tcm4TlvDq8ikWAM",
    "Domi (energetic, anime-like)": "AZnzlk1XvdvUeBnXmlld",
    "Dorothy (cute, high-pitched)": "ThT5KcBeYPX3keUQqHPh",
    "Bella (young, cheerful)": "EXAVITQu4vr4xnSDxMaL",
    "Antoni (if you want male voice)": "ErXwobaYiN019PkySvjV"
}

# Try with Domi - usually good for anime-style content
elevenlabs_tts(text, "paimon_voice.mp3", voice_id=voices["Rachel (young, expressive)"], api_key="sk_c89c3f52621e787ac831bb835159cffede08cd8d8c960c9f")