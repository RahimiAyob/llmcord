import discord
from discord.ext import commands
from discord.app_commands import Choice
from openai import AsyncOpenAI
import yaml
import json
import os
import edge_tts
import asyncio

# Load config
with open("config.yaml", encoding= 'utf-8') as f:
    config = yaml.safe_load(f)

# Setup bot and client
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
client = AsyncOpenAI(
    base_url="https://api.deepseek.com/v1",
    api_key=config["deepseek_api_key"]
)

# Global model setting
current_model = "deepseek-chat"

# Conversation storage file
CONVERSATION_FILE = "conversations.json"


def save_conversations():
    """Save conversations to file"""
    with open(CONVERSATION_FILE, 'w', encoding='utf-8') as f:
        json.dump(conversations, f, indent=2, ensure_ascii=False)


def load_conversations():
    """Load conversations from file"""
    if os.path.exists(CONVERSATION_FILE):
        try:
            with open(CONVERSATION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Failed to load conversations: {e}")
    return {}


# Load existing conversations on startup
conversations = load_conversations()


def get_conversation_key(obj):
    """Get unique key for conversation (channel, thread, or DM) for Message or Interaction."""
    # For discord.Message
    if hasattr(obj, 'thread') and obj.thread is not None:
        return f"{obj.guild.id if obj.guild else 'dm'}_thread_{obj.thread.id}"
    if hasattr(obj, 'channel') and isinstance(obj.channel, discord.Thread):
        return f"{obj.guild.id if obj.guild else 'dm'}_thread_{obj.channel.id}"
    # For discord.Interaction
    if hasattr(obj, 'channel') and hasattr(obj, 'guild'):
        return f"{obj.guild.id if obj.guild else 'dm'}_{obj.channel.id}"
    # Fallback
    return "unknown"


# Load personalities from config
PERSONALITIES = config.get("personalities", {})

# Store selected personality per conversation key
conversation_personalities = {}


@bot.tree.command(name="model", description="Switch between DeepSeek models")
async def model_command(interaction: discord.Interaction, model: str):
    global current_model

    if interaction.user.id not in config.get("admin_ids", []):
        await interaction.response.send_message("Only admins can switch models.", ephemeral=True)
        return

    current_model = model
    await interaction.response.send_message(f"Switched to: **{model}**")


@model_command.autocomplete("model")
async def model_autocomplete(interaction: discord.Interaction, current: str):
    models = ["deepseek-chat", "deepseek-reasoner"]
    return [Choice(name=m, value=m) for m in models if current.lower() in m.lower()]


@bot.tree.command(name="debug", description="Show conversation storage (admin only)")
async def debug_command(interaction: discord.Interaction):
    if interaction.user.id not in config.get("admin_ids", []):
        await interaction.response.send_message("Admin only!", ephemeral=True)
        return

    if not conversations:
        await interaction.response.send_message("No conversations stored yet.")
        return

    debug_info = []
    for key, msgs in conversations.items():
        debug_info.append(f"**{key}**: {len(msgs)} messages")

    debug_info.append(f"\nFull conversations saved in: `{CONVERSATION_FILE}`")
    result = "\n".join(debug_info)
    await interaction.response.send_message(result)


@bot.tree.command(name="clear", description="Delete this thread")
async def clear_command(interaction: discord.Interaction):
    # Only allow in threads
    if not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message("You can only use /clear inside a thread.", ephemeral=True)
        return
    try:
        thread_name = interaction.channel.name
        await interaction.response.send_message(f"Deleting this thread: {thread_name}", ephemeral=True)
        await interaction.channel.delete(reason=f"/clear command used by {interaction.user.display_name}")
    except Exception as e:
        await interaction.response.send_message(f"Failed to delete thread: {e}", ephemeral=True)


@bot.tree.command(name="chat", description="Start a new chat thread with Aiko-chan or a selected personality")
@discord.app_commands.describe(
    title="Optional: Title for the thread",
    personality="Optional: Choose a personality for this chat",
    visibility="Optional: Who can see this thread (public or private)"
)
@discord.app_commands.choices(personality=[
    Choice(name=name, value=name) for name in PERSONALITIES.keys()
])
@discord.app_commands.choices(visibility=[
    Choice(name="Public (everyone can see)", value="public"),
    Choice(name="Private (only invited can see)", value="private")
])
async def chat_command(
    interaction: discord.Interaction,
    title: str = None,
    personality: str = None,
    visibility: str = "public"
):
    # Only allow in text channels (not DMs)
    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message("This command can only be used in a server text channel.", ephemeral=True)
        return

    # Set thread name
    if title:
        thread_name = title
    else:
        thread_name = f"Chat Thread - {interaction.user.display_name}"

    # Set thread type
    if visibility == "private":
        thread_type = discord.ChannelType.private_thread
    else:
        thread_type = discord.ChannelType.public_thread

    # Create thread from the command invocation message
    thread = await interaction.channel.create_thread(
        name=thread_name,
        type=thread_type,
        auto_archive_duration=60  # 1 hour
    )

    # Set personality for this thread if provided
    conv_key = f"{interaction.guild.id}_thread_{thread.id}"
    if personality and personality in PERSONALITIES:
        conversation_personalities[conv_key] = personality
        # Try to set bot nickname in the guild
        if interaction.guild:
            try:
                me = interaction.guild.me or await interaction.guild.fetch_member(bot.user.id)
                await me.edit(nick=personality)
            except Exception as e:
                personality_msg = f"Personality set to **{personality}** for this chat! (Could not change bot nickname: {e})"
            else:
                personality_msg = f"Personality set to **{personality}** for this chat!"
        else:
            personality_msg = f"Personality set to **{personality}** for this chat!"
    else:
        personality_msg = "💬 **No personality selected** - I'll respond as raw DeepSeek AI. Use `/personality` to add a personality if you want!"

    await thread.send(personality_msg)
    await interaction.response.send_message(f"Thread created: {thread.mention} ({'public' if thread_type==discord.ChannelType.public_thread else 'private'})", ephemeral=True)


@bot.tree.command(name="personality", description="Select a personality for this chat")
@discord.app_commands.describe(personality="Choose a personality")
@discord.app_commands.choices(personality=[
    Choice(name=name, value=name) for name in PERSONALITIES.keys()
])
async def personality_command(interaction: discord.Interaction, personality: str):
    conv_key = get_conversation_key(interaction)
    conversation_personalities[conv_key] = personality
    # Try to set bot nickname in the guild
    if interaction.guild:
        try:
            me = interaction.guild.me or await interaction.guild.fetch_member(bot.user.id)
            await me.edit(nick=personality)
        except Exception as e:
            await interaction.response.send_message(f"Personality set to: **{personality}** (Could not change bot nickname: {e})", ephemeral=True)
            return
    await interaction.response.send_message(f"Personality set to: **{personality}**", ephemeral=True)


# Track active calls: {thread_id: voice_client}
active_calls = {}

# Path to ffmpeg executable (set this to your ffmpeg.exe location)
FFMPEG_PATH = r"C:\ffmpeg-2025-08-20-git-4d7c609be3-full_build\ffmpeg-2025-08-20-git-4d7c609be3-full_build\bin\ffmpeg.exe"


@bot.tree.command(name="call", description="Start a voice call: bot will join your voice channel and speak replies")
async def call_command(interaction: discord.Interaction):
    # Only allow in threads
    if not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message("You can only use /call inside a thread.", ephemeral=True)
        return
    # Check if user is in a voice channel
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("You must be in a voice channel to start a call.", ephemeral=True)
        return
    voice_channel = interaction.user.voice.channel
    # Join the voice channel
    try:
        voice_client = await voice_channel.connect()
        active_calls[interaction.channel.id] = voice_client
        await interaction.response.send_message(f"Joined voice channel: {voice_channel.name}. I will speak my replies here!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to join voice channel: {e}", ephemeral=True)


async def tts_and_play(text, voice_client):
    # Use edge-tts to generate TTS audio and play in the voice channel
    try:
        communicate = edge_tts.Communicate(text, voice="en-US-AriaNeural")
        wav_path = "tts_output.wav"
        await communicate.save(wav_path)
        audio_source = discord.FFmpegPCMAudio(wav_path, executable=FFMPEG_PATH)
        if not voice_client.is_playing():
            voice_client.play(audio_source)
            # Wait for playback to finish
            while voice_client.is_playing():
                await asyncio.sleep(0.5)
    except Exception as e:
        print(f"TTS error: {e}")


@bot.tree.command(name="leave", description="Disconnect the bot from the voice channel for this thread")
async def leave_command(interaction: discord.Interaction):
    # Only allow in threads
    if not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message("You can only use /leave inside a thread.", ephemeral=True)
        return
    thread_id = interaction.channel.id
    if thread_id in active_calls:
        voice_client = active_calls[thread_id]
        try:
            await voice_client.disconnect()
            del active_calls[thread_id]
            await interaction.response.send_message("Left the voice channel for this thread.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed to leave voice channel: {e}", ephemeral=True)
    else:
        await interaction.response.send_message("I'm not in a voice channel for this thread.", ephemeral=True)


@bot.event
async def on_ready():
    # Sync commands to each guild for instant availability
    for guild in bot.guilds:
        try:
            await bot.tree.sync(guild=guild)
            print(f"[SYNC] Synced commands to {guild.name} ({guild.id})")
        except Exception as e:
            print(f"[SYNC] Failed to sync to {guild.name}: {e}")

    # Also try global sync (may take a few minutes to appear)
    try:
        await bot.tree.sync()
        print("[SYNC] Global command sync complete.")
    except Exception as e:
        print(f"[SYNC] Global sync failed: {e}")

    print(f"Bot ready! Current model: {current_model}")
    print("Commands available: /chat, /personality, /call, /leave, /clear, /model, /debug")


@bot.event
async def on_message(msg):
    # Skip if bot message
    if msg.author.bot:
        return

    # Only respond in threads or DMs
    if not isinstance(msg.channel, discord.Thread) and msg.guild is not None:
        return

    # Clean message content
    content = msg.content.replace(f"<@{bot.user.id}>", "").strip()
    if not content:
        return

    try:
        # Get conversation history
        conv_key = get_conversation_key(msg)
        if conv_key not in conversations:
            conversations[conv_key] = []

        # Add user message to history
        conversations[conv_key].append({"role": "user", "content": content})

        # Keep only last 10 exchanges (20 messages)
        if len(conversations[conv_key]) > 20:
            conversations[conv_key] = conversations[conv_key][-20:]

        # Save to file after adding user message
        save_conversations()

        # Check if personality is selected - if not, use no system prompt (raw DeepSeek)
        personality_name = conversation_personalities.get(conv_key)

        # Build messages for API
        messages = conversations[conv_key].copy()

        # Add system prompt only if a personality is selected
        if personality_name and personality_name in PERSONALITIES:
            system_prompt = PERSONALITIES[personality_name]
            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt.replace("{username}", msg.author.display_name)
                })

        # Get response
        async with msg.channel.typing():
            response = await client.chat.completions.create(
                model=current_model,
                messages=messages
            )

        reply = response.choices[0].message.content

        # Add bot response to history
        conversations[conv_key].append({"role": "assistant", "content": reply})

        # Save to file after bot response
        save_conversations()

        # Send response (split if too long)
        if len(reply) > 2000:
            chunks = [reply[i:i + 2000] for i in range(0, len(reply), 2000)]
            for chunk in chunks:
                await msg.reply(chunk)
        else:
            await msg.reply(reply)

        # TTS: If a call is active for this thread, speak the reply
        if isinstance(msg.channel, discord.Thread) and msg.channel.id in active_calls:
            voice_client = active_calls[msg.channel.id]
            await tts_and_play(reply, voice_client)

    except Exception as e:
        await msg.reply(f"Error: {e}")


bot.run(config["bot_token"])
