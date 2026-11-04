# DESIGN.md — escape-silkboard

### 1. The moment — What did you design for?
I designed for the moment at **Hebbal Flyover around 8:30 PM** when battery drops below **10%** and cash is under **₹150**. Watching the live route bar inch toward the airport while reading the driver's blunt quote in bold typography creates real panic before every move.

### 2. The cut — What did you leave out?
I cut preset multiple-choice action buttons and complex side-menus. Preset buttons turn an open-ended text adventure into a multiple-choice quiz. Stripping them out kept the focus on plain-English input, a two-part chat hierarchy (bold driver speech + subtle scene note), and the **Live Route Map**.

### 3. The miss — Where was the AI wrong?
Initially, Gemini moved the map and deducted cash even when the player only asked an auto driver for the fare, and once accepted UPI at `0%` battery. I fixed this with a deterministic Python guardrail (`OutputGuardrail`) that enforces stationary haggling (`0 km`, `₹0`), wallet caps, and a `0%` battery lock.
