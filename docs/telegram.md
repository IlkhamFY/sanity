# Telegram

Three people and three Hermes bots share one Telegram group. One bot per role: Reader, Verifier, Writer. The group is where the humans watch and steer. It is not the bus the bots use to hand work to each other. That bus is the repo. See [docs/handoff.md](handoff.md).

Who holds which bot is in [docs/setup.md](setup.md). That assignment is editable.

## Who is in the group

| | Role |
| --- | --- |
| Reader bot | Extracts equations into `runs/<slug>/equations.json`. |
| Verifier bot | Writes `runs/<slug>/verify/` and `RESULTS.md`. Confirms or rejects each flag from the script verdict and from Lean. |
| Writer bot | Writes `runs/<slug>/REPORT.md` and `telegram.md`. Does not change a verdict. |
| Three people | @mention a bot to trigger it. Approve a `PLAN.md`, reject a section, or ask for a step to be run again. |

Each agent is its own bot. Create three bots with [@BotFather](https://t.me/BotFather). One token per bot. Do not reuse a token across agents.

## Privacy mode off

In BotFather, disable privacy mode for each bot: `/setprivacy`, choose the bot, **Disable**.

Then remove that bot from the group and add it again. Telegram keeps the old privacy setting until the bot is re-added.

With privacy mode on, a bot in a group only sees commands, replies to itself, and mentions, and the client can show that the bot has no access to messages. The humans' steering messages would be invisible. Privacy mode off delivers human messages to every bot. It still does not deliver one bot's messages to another bot.

If a bot still shows "has no access to messages" after the change, privacy is still on. Disable it again and re-add the bot. [docs/setup.md](setup.md) calls this out for the Writer bot, which has been seen in that state.

## Bots cannot see other bots

In a group, the Bot API does not deliver one bot's messages to another bot. The Reader's post never arrives at the Verifier. The Verifier's note never arrives at the Writer. The group transcript is for the people.

## How a turn works

Humans @mention the bot that should act. That is the trigger.

The bot pulls the repo, acts only when `runs/<slug>/status.json` has its stage, commits, pushes, and posts one line:

```
@<next-bot> runs/<slug> ready
```

The Writer's last line is `runs/<slug> ready`. The short human summary is the file `runs/<slug>/telegram.md`, not a second chat thread between bots.

No agent should scrape the group for another agent's text.

## Who may talk to a bot

Lock each bot to the team's Telegram user IDs. Put the three numeric IDs in the profile environment as `TELEGRAM_ALLOWED_USERS`, and in `platforms.telegram.extra.allow_from` in the example config. Do not use `*` .

Group messages should require a mention (`telegram.require_mention: true`), so ordinary chatter does not start a run.

## Tokens

Keep the three BotFather tokens out of the repository. Hermes reads `TELEGRAM_BOT_TOKEN` from the profile environment, not from git. While you are setting a machine up, a separate name per bot is enough: `READER_TELEGRAM_TOKEN`, `VERIFIER_TELEGRAM_TOKEN`, `WRITER_TELEGRAM_TOKEN`. Copy the value into `TELEGRAM_BOT_TOKEN` for that profile. This skeleton does not call Telegram.
