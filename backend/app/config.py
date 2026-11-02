import os

from dotenv import load_dotenv

load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./watchparty.db")

# Single local user for now; every row still carries a user_id so groups can come later.
LOCAL_USER_ID = 1
