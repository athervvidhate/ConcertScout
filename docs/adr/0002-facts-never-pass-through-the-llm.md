# Facts never pass through the LLM

A Concert's facts (names, dates, venues, prices, URLs, images) come only from its source. The ranker grades candidates by ID and writes a reason for each one shown; code rejects unknown IDs and fills in the facts from the source record. The previous design had the model re-emit every concert, which risked corrupting ticket links and made each search slow and expensive. Giving the ranker no tools and only short structured fields also limits prompt injection through event text.
