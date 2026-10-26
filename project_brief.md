# My agent: PaceCraft (Running Coach Agent)

One-liner: A conversational coach that helps runners of any level create and manage personalized training plans with a catalog of structured workouts and milestone goals.

Tool coverage:
- Memory: User's baseline fitness/current weekly mileage, target race/distance (e.g., 5K, 10K, Half Marathon, Marathon), target date/event timeline, injury history, and preferred running days.
- Tools: Generate custom weekly training schedules (including walk-run intervals and splits for beginners or interval training when required), calculate target training paces (easy, tempo, interval), log completed runs, and adjust future weeks based on progress or missed workouts.
- Catalog/UI: Catalog of workouts (Intervals, Tempo runs, Long runs, Recovery runs, Cross-training routines) rendered as A2UI schedule cards and weekly summary tables.
- Image gen: Motivational visual cards, milestone race badges, or training route inspiration maps.
- Sandbox: Paces and splits calculator (e.g., Jack Daniels VDOT / Riegel formula calculations to project finish times and pacing splits).

Recommended for every project: memory, storage, tools, image generation, A2UI
Agent-specific / stretch (pick what fits): Code sandbox for VDOT / pace calculations, Firestore for tracking logged workouts over time, live weather API lookup for daily run advice.
