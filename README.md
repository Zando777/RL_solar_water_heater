# RL_solar_water_heater
Personal project to explore the use of Q-learning, weather API, and a MQTT server to intelligently control a solar hot water pump. Very much a WIP and is waiting long term deployment.

There are fundemental issues with the underlying ML archetecture, therefore next steps would be:

- Build a simulator/digital twin (tank thermodynamics + solar model).
- Use model-based RL or policy gradient methods (instead of tabular Q-learning).
- Encode constraints & safety (e.g., never let tank < 40 °C).
- Define a multi-objective reward: efficiency, comfort, safety.
- Compare against a rule-based baseline.

Project Structure:
src/
esp32/ # ESP32 firmware for MQTT bridge
arduino_mega/ # Arduino Mega sensor + control firmware
python/ # Reinforcement Learning controller
docs/ # Documentation (architecture diagram)

🚀 What we’re optimizing

Primary goal: maximize energy absorbed from solar → increase tank temperature during solar hours.

Efficiency: avoid wasting electricity → penalize running the pump when panels aren’t hotter than tank, or when sun is weak.

Stability & safety: avoid rapid switching; respect max/min tank temperatures.

🧠 Improved State (Markov-ish, compact, RL-friendly)

We’ll discretize continuous signals so your Q-table stays tractable:

Raw signals

temp_in (to panels), temp_out (from panels), tank_temp

ΔT_panel = temp_out - temp_in (panel heat gain)

ΔT_tank = tank_temp - prev_tank_temp (tank change per step)

Weather: is_day, cloud_cover (0–100), and a sun factor from time-of-day vs sunrise/sunset (0–1)

Time-of-day bucket: early AM / mid-day / afternoon / evening

last_action (0/1) to give the agent inertia context

Discretization (bins)

tank_bin: e.g., 20–80 °C in 5 °C steps

panel_delta_bin: e.g., <−5, −5–0, 0–3, 3–6, >6 °C

sun_bin: 0 (night) / 1 (low) / 2 (medium) / 3 (high)

cloud_bin: 0 (clear ≤20%), 1 (partly 20–60%), 2 (overcast >60%)

tod_bin: 0 early (sunrise–10), 1 mid (10–14), 2 late (14–sunset), 3 off-hours

last_action (0/1)

State tuple

state = (
  tank_bin,
  panel_delta_bin,
  sun_bin,
  cloud_bin,
  tod_bin,
  last_action
)


This is compact, informative, and largely satisfies the Markov property for this domain.

🎯 Reward shaping (what “good” looks like)

Per message step (e.g., every 2–10s):

Let ΔTank = tank_temp - prev_tank_temp

Positive reward for raising tank temp during daylight, scaled by sun factor

Penalty for running pump (electricity) — constant per step if ON

Penalty for inefficient pumping when temp_out ≤ temp_in

Penalty for chatter (frequent switching)

Safety penalties for overheating or too-cold tank

Formula (step)

reward =
  + α * ΔTank * sun_factor
  + β * max(0, ΔT_panel) * (action==ON)         # tiny shaping to prefer real heat gain
  - γ * (action==ON)                             # running cost
  - δ * switch_penalty                           # if toggled too soon
  - λ_hot * [tank_temp > T_MAX]
  - λ_cold * [tank_temp < T_MIN]


Typical weights (start here, tune later)

α = 10.0 # value of raising tank temp during sun

β = 0.5 # small bonus for real panel heat when ON

γ = 0.2 # pump cost per step

δ = 0.5 # discourage flipping

λ_hot = 5.0 # safety (hard penalty if too hot)

λ_cold = 1.0 # comfort floor penalty (optional)

Extras

Solar-hours bonus: set sun_factor = 0 at night; ≈1 at strong sun.

Switching guardrail: disallow flips within MIN_ON_TIME/MIN_OFF_TIME.

Terminal shaping (optional): at sunset, add a small bonus for final tank temp relative to morning; you can implement later if you log daily stats.

Setup Instructions

1. Install MQTT Broker
On macOS:
'''bash
brew install mosquitto
brew services start mosquitto

2. Python Environment
python3 -m venv my_rl_env
source my_rl_env/bin/activate
pip install -r requirements.txt

3. Run the RL Controller
cd src/python
python rl_controller.py

4. Flash ESP32

Upload esp32_mqtt_bridge.ino to the ESP32 (via Arduino IDE).

5. Flash Arduino Mega

Upload mega_sensors.ino to the Mega (via Arduino IDE).


📡 MQTT Topics

Publish: waterheater/sensor_data → "temp_in,temp_out,tank_temp"

Subscribe: waterheater/pump_control → "ON" or "OFF"

🧠 RL Agent

Uses Q-learning with epsilon-greedy exploration

State space: (temp_in, temp_out, tank_temp)

Reward:

+1 when pumping heat efficiently (panel hotter than tank)
-1 when pumping inefficiently

Weather data integration via OpenWeatherMap (cloud cover, sunrise/sunset, etc.)

📊 Visualization

The agent plots tank temperature over time and logs last communication time from the MQTT broker.
