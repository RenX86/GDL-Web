gallery-dl-webapp/
│
├── run.py                 # Application runner
├── config.py              # Configuration management
├── requirements.txt       # Python dependencies
├── app/
│   ├── __init__.py       # Flask app factory
│   ├── routes.py         # All route handlers
│   └── services.py       # Business logic & download service
├── templates/
│   └── index.html        # Frontend HTML
├── downloads/            # Downloaded files (auto-created)
├── app.log               # Application logs (auto-created)
└── .env                  # Environment variables (optional)