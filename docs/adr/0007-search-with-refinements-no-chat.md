# Search with Refinements, no open-ended chat

Concert Scout was initially scoped as a single-shot Search product with no chat. In practice, people often see what is wrong with a Poster without wanting to rewrite the whole Search: they want only weekends, a lower price ceiling, a nearby city like Oakland, or more Artists like the second pick on screen.

We replace "No chat" with **Search with Refinements, no open-ended chat**. A Refinement is a short typed follow-up under the Poster that updates the current Reading and produces a new Poster. Earlier Refinements appear as a horizontal trail of undoable chips, not as chat bubbles or a conversation thread.

Every Refinement runs through a single structured Haiku call with no tools, seeing only the current Reading, the ordered Artist names on the current Poster, and the Refinement text. It never sees visitor coordinates, imported Taste beyond what the Reading holds, Spotify account data (ADR 0003), or Concert listing text other than Artist names. Code validates the returned Reading against the same bounds as a typed Search.

Open-ended questions that a Reading cannot express — such as "is it all ages?", "where do I park?", or "what time do doors open?" — have no answer in the source record. Answering them would require the model to invent facts, violating ADR 0002. Instead, the Refinement call classifies them as unanswerable, and Concert Scout shows a plain inline note saying it cannot tell, with the Concert's source ticket link, without running a new Search.

When a Refinement only narrows dates, place radius, weekdays, or price relative to the current Reading and the Search's cached pool session is still in Redis, code filters the cached shortlist and reuses the cached Jev grades with zero ranker or source calls. Every Refinement still counts as one Search against the per-visitor hourly limit and the daily and monthly spend caps.
