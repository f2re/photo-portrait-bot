# HeadshotPro AI — Business Portrait Bot

Telegram bot for generating professional business portraits and corporate headshots from selfies using AI.

## Features

- 📸 **Automatic Business Portrait Generation**: Converts casual photos into high-end studio portraits (navy blue suit, studio lighting, charcoal background).
- 🤖 **AI-Powered**: Uses advanced AI (OpenRouter/Gemini 2.5) for photorealistic results.
- 📄 **Document Support**: Supports sending photos as documents for lossless quality.
- 📦 **Batch Processing**: Send multiple photos as an album to process them all at once.
- 💳 **Integrated Payments**: Purchase image packages via YooKassa.
- 👥 **Referral Program**: Invite friends and earn free processing credits.
- 📊 **Analytics**: Tracks usage and sales (Yandex Metrika integration).

## Tech Stack

- **Python 3.11+**
- **aiogram 3.x**
- **PostgreSQL** (SQLAlchemy + Alembic)
- **Redis** (for caching/FSM if configured)
- **OpenRouter API** (AI Image Processing)
- **YooKassa** (Payments)

## Setup

1. **Clone the repository**
2. **Configure Environment**:
   Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   nano .env
   ```
   Required:
   - `BOT_TOKEN`
   - `OPENROUTER_API_KEY`
   - `DATABASE_URL`
   - `ADMIN_IDS`

3. **Run with Docker (Recommended)**:
   ```bash
   docker-compose up -d
   ```

4. **Run Locally**:
   ```bash
   # Install dependencies
   pip install -r requirements.txt
   
   # Run migrations
   alembic upgrade head
   
   # Start bot
   python -m app.bot
   ```

## Project Structure

- `app/` - Main application code
  - `bot.py` - Entry point
  - `handlers/` - Telegram update handlers
  - `services/` - External services (AI, Payments)
  - `database/` - DB models and CRUD
- `alembic/` - Database migrations

## License

MIT