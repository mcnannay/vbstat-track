# Volleyball Stats Tracker

A small Flask + SQLite web app for tracking volleyball match stats.

## Features

- Settings page for players: name, number, position, and photo upload
- Default stat categories: Dig, Kill, Assist, Ace, Service Error, Block
- Add custom stat categories from Settings
- Create new matches and view old matches
- Player grid for recording stats during a match
- Next-set button prompts for previous set score
- Match summary with set scores and stat totals
- Docker and Portainer ready

## Local Docker run

```bash
cp .env.example .env
docker compose up --build -d
```

Open:

```text
http://localhost:5000
```

## Deploy with Portainer from GitHub

1. Upload this folder to a GitHub repository.
2. In Portainer, go to **Stacks** → **Add stack**.
3. Choose **Repository**.
4. Paste your GitHub repo URL.
5. Set **Compose path** to:

```text
portainer-stack.yml
```

6. Add these environment variables in Portainer:

```text
SECRET_KEY=replace-with-a-long-random-string
TZ=America/Los_Angeles
```

7. Deploy the stack.

The app will be available on:

```text
http://YOUR_SERVER_IP:5000
```

## Persistent data

The Portainer stack creates two Docker named volumes:

- `volleyball_stats_data` stores the SQLite database
- `volleyball_stats_uploads` stores player photos

Do not delete those volumes unless you want to reset the app.

## Repo layout

```text
app.py                  Flask application
Dockerfile              App container build
docker-compose.yml      Local compose file
portainer-stack.yml     Portainer stack file
templates/              HTML templates
static/style.css        Styling
static/uploads/         Player photo uploads
```
