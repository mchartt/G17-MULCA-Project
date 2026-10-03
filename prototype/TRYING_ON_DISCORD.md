# Trying MULCA on Discord

This guide takes you from nothing to MULCA talking in a Discord voice channel. It uses a private test server, linked to your own bot from Discord, so nobody else's setup is touched.

## 1. One-time setup (about 15 min)

1. **Create a test server.** In Discord, choose *Add a Server* → *Create My Own*. In it, create a text channel `#mulca-test` and a voice channel `MULCA voice`.
2. **Create the bot.** Go to <https://discord.com/developers/applications> and choose *New Application*.
   - On the **Bot** page, choose *Reset Token* and copy the token.
   - On the same page, turn on **Message Content Intent** and **Server Members Intent**.
3. **Invite the bot.** Go to **OAuth2 → URL Generator**.
   - Scopes: `bot` and `applications.commands` (for `/restart` and `/mulca`).
   - Permissions: View Channels, Send Messages, Read Message History, Connect, Speak, Use Voice Activity.
   - Open the generated URL and add the bot to the test server.
4. **Optional:** a second person, or a second account in a browser, for the multi-person steps.

## 2. Configuration

Create `.env`:

```bash
DISCORD_BOT_TOKEN=...
MULCA_VOICE_DEBUG_DIR=voice-debug
```

Which channels MULCA serves is set from Discord once the bot runs (step 3), and kept in `data/mulca.db` (git-ignored).

## 3. Start

1. **Start MUCA-Server.** It needs `OPENAI_API_KEY` in its environment or in `MUCA-Server/.env`:

   ```bash
   cd ../../MUCA-Server && python -m muca_server.run_server
   ```

2. **Start the bot:**

   ```bash
   python -m mulca_discord
   ```

3. **Link the channels.** In `#mulca-test`, type `/mulca link`, set `voice` to `MULCA voice` and `transcripts` to True (to see what MULCA says out loud), and send it. Only you see the reply.

4. **Optional: run the preflight check.** Stop the bot (Ctrl+C) first, since both would use the same bot account. Then, while you sit in `MULCA voice`:

   ```bash
   python -m mulca_discord.preflight --voice-test 10
   ```

   Every line should say PASS. Talk while it records, then listen to `voice-test/<your id>.wav`. **If it isn't clearly your voice, stop here** and see [Troubleshooting](#5-troubleshooting). Then start the bot again.

## 4. What to try

Watch the MUCA-Server terminal. For every turn it logs who spoke (the trigger variables) and the intervention decision.

| # | Do | Expect |
|---|---|---|
| 1 | Type `@mainllm say hi` in `#mulca-test` | A text reply. This is the forced path, which skips the intervention agent's judgement. |
| 2 | Join `MULCA voice` | The bot joins within about 1–2 s. |
| 3 | Talk for about 5 s about anything | The bot's log shows packet counters rising every 10 s, with `dave_failed=0`. `voice-debug/*.wav` sounds like you. MUCA-Server logs a turn under your name, and MULCA most likely stays quiet. |
| 4 | Say "Hey MULCA, what's the capital of France?" | A spoken answer within about 2–3 s. Its transcript appears in `#mulca-test`. |
| 5 | Say "MULCA, tell me a long story", then talk over it | MULCA stops within about 0.5 s. |
| 6 | Say a fact out loud, then type `@mainllm` and ask about it | The text reply knows the fact, because text and voice share one memory. |
| 7 | With a second person, take turns, then let one person dominate | Each turn is logged under the right name. Eventually `participation_equality` fires. |
| 8 | DM the bot: "what did we talk about in voice?" | "I don't take direct messages here": DMs are off by default. |
| 9 | In `#mulca-test`, run `/mulca dms enabled:True`, then DM the same question | A private reply that knows the group's recent talk. |
| 10 | Stop MUCA-Server with Ctrl+C, restart it, and keep talking | The bot reconnects and still remembers the fact from step 6. |
| 11 | Everyone leaves the voice channel | The bot leaves too. |

## 5. Troubleshooting

| Symptom | Likely cause | Look at |
|---|---|---|
| The preflight says intents are missing | A toggle on the portal's Bot page is off | Developer portal → Bot |
| The voice-test WAV is noise | DAVE frames were decoded without being decrypted | The `dave_failed` and `dave_passthrough` counters; `voice/capture.py` `_undo_dave` |
| The voice-test WAV is silent and `packets=0` | Voice receive isn't working | Run with `logging.DEBUG`; check the `discord-ext-voice-recv` version |
| MUCA-Server never logs a voice turn | The floor was never taken, or the provider's VAD never fired | Loudness of `voice-debug/*.wav` and its `.floor.txt`; `voice/synchronizer.py` threshold |
| A turn is logged, but MULCA doesn't answer | The intervention agent decided to say nothing | The "intervention decision" line; address MULCA by name |
| MULCA stopped answering, by text and voice | Its OpenAI connection ended and the session didn't recover | Type `/restart` in its channel; `/mulca status` shows the session; MUCA-Server's log |
| MULCA answers but can't be heard | The bot lacks Speak permission, or playback didn't start | Preflight permissions; `voice/bridge.py` `_ensure_playing` |
