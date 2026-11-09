# Use only official Spotify access

Spotify is reached only through official OAuth, for the owner and allowlisted friends, and everyone else brings Taste through Last.fm, a user-held history file, or a pasted list. Unofficial clients such as SpotAPI and librespot were rejected: they authenticate with a password or session cookie, so the server would hold full account access, which cannot be made safe, and they break Spotify's terms in a public portfolio repo. Spotify data also stays out of LLM prompts because Developer Policy clause III.14 restricts feeding it to AI models.
