import numpy as np
import paho.mqtt.client as mqtt
import random
import pickle
import matplotlib.pyplot as plt
import requests
import datetime
import os

# MQTT Settings
MQTT_BROKER = "localhost"  # Mac running mosquitto
MQTT_PORT = 1883
MQTT_TOPIC_SENSOR = "waterheater/sensor_data"
MQTT_TOPIC_CONTROL = "waterheater/pump_control"

# RL Parameters
learning_rate = 0.1
discount_factor = 0.9
exploration_rate = 1.0
min_exploration_rate = 0.01
exploration_decay = 0.995

# ====== CONFIG (tune for your system) ======
TANK_MIN_C = 35.0      # comfort/safety lower bound
TANK_MAX_C = 75.0      # safety upper bound

# Reward weights
ALPHA = 10.0           # weight for ΔTank during sun
BETA  = 0.5            # small shaping for real panel heat when ON
GAMMA = 0.2            # pump running cost per step
DELTA = 0.5            # switching penalty weight
LAMBDA_HOT  = 5.0      # penalty for overheating
LAMBDA_COLD = 1.0      # penalty for too cold (optional)

# Switching guardrails
MIN_ON_TIME_S  = 30.0  # seconds to stay ON before allowed to switch
MIN_OFF_TIME_S = 20.0  # seconds to stay OFF before allowed to switch

# ====== GLOBALS to track dynamics ======
prev_tank_temp = None
last_action = 0               # 0=OFF, 1=ON
last_switch_time = None       # epoch seconds when last toggled

# Q-Table
Q_table = {}
Q_TABLE_FILE = "q_table.pkl"
tank_temp_history = []

def save_q_table():
    with open(Q_TABLE_FILE, "wb") as f:
        pickle.dump(Q_table, f)
    print("[💾] Q-table saved!")

def load_q_table():
    global Q_table
    if os.path.exists(Q_TABLE_FILE):
        with open(Q_TABLE_FILE, "rb") as f:
            Q_table = pickle.load(f)
        print("[🔄] Q-table loaded!")
    else:
        print("[⚠️] No saved Q-table found, starting fresh.")

load_q_table()

# Actions: 0 = OFF, 1 = ON
actions = [0, 1]

def get_state(temp_in, temp_out, tank_temp, weather):
    """
    Discrete, compact, Markov-ish state for tabular Q-learning.
    """
    # Derived signals
    panel_delta = temp_out - temp_in

    # Time features
    now = datetime.datetime.now()
    sunrise = weather.get("sunrise")
    sunset  = weather.get("sunset")
    is_day  = 1 if sunrise and sunset and (sunrise < now < sunset) else 0
    sf      = sun_factor_from_clock(now, sunrise, sunset)  # 0..1

    # Buckets
    tank_bin = bin_val(tank_temp, [25, 35, 45, 55, 65, 75, 85])          # 7 bins
    panel_delta_bin = bin_val(panel_delta, [-5, 0, 3, 6])                # 5 bins
    # sun bin from continuous sun factor
    sun_bin = bin_val(sf, [0.25, 0.5, 0.75])                             # 4 bins: 0 night/low..3 high
    cloud = weather.get("cloud_cover", 50)
    cloud_bin = bin_val(cloud, [20, 60])                                 # 3 bins: clear/partial/overcast

    # Time of day buckets (clock-hours) — only meaningful when is_day=1
    hr = now.hour
    if not is_day:
        tod_bin = 3  # off-hours
    else:
        if hr < 10:   tod_bin = 0
        elif hr < 14: tod_bin = 1
        else:         tod_bin = 2

    # Include last action to give the agent inertia context
    global last_action
    return (tank_bin, panel_delta_bin, sun_bin, cloud_bin, tod_bin, int(last_action))


def get_best_action(state):
    if state not in Q_table:
        Q_table[state] = [0, 0]
    return np.argmax(Q_table[state])

def update_q_table(state, action, reward, next_state):
    if state not in Q_table:
        Q_table[state] = [0, 0]
    if next_state not in Q_table:
        Q_table[next_state] = [0, 0]
    Q_table[state][action] += learning_rate * (
        reward + discount_factor * max(Q_table[next_state]) - Q_table[state][action]
    )

def bin_val(x, edges):
    """Return index of bin for value x given ascending edges (right-open)."""
    for i, e in enumerate(edges):
        if x < e:
            return i
    return len(edges)

def sun_factor_from_clock(now, sunrise, sunset):
    """0 at night; ramp up to 1 near solar noon; down near sunset."""
    if sunrise is None or sunset is None or not (sunrise < now < sunset):
        return 0.0
    # Normalize time between sunrise and sunset to [0,1]
    span = (sunset - sunrise).total_seconds()
    x = (now - sunrise).total_seconds() / max(1.0, span)
    # Smooth bell-like shape peaking at solar noon (~x=0.5)
    return max(0.0, 1.0 - 4 * (x - 0.5) ** 2)  # parabola opening downward


def decide_action(state):
    global exploration_rate
    if random.uniform(0, 1) < exploration_rate:
        action = random.choice(actions)
    else:
        action = get_best_action(state)
    if exploration_rate > min_exploration_rate:
        exploration_rate *= exploration_decay
    return action

def calculate_reward(temp_in, temp_out, tank_temp, action, weather):
    """
    Shaped step reward:
      + improve tank temp during sun,
      + small bonus for real panel heat when ON,
      - cost to run pump,
      - penalty for chattering,
      - safety penalties for too-hot/too-cold.
    """
    global prev_tank_temp, last_action, last_switch_time

    now = datetime.datetime.now()
    sunrise = weather.get("sunrise")
    sunset  = weather.get("sunset")
    sf = sun_factor_from_clock(now, sunrise, sunset)  # 0..1

    # ΔTank (handle first step)
    if prev_tank_temp is None:
        delta_tank = 0.0
    else:
        delta_tank = tank_temp - prev_tank_temp

    # Panel delta (proxy for useful heat)
    panel_delta = temp_out - temp_in

    # Base reward: encourage raising tank temp when sun is available
    reward = ALPHA * (delta_tank * sf)

    # Shaping: if ON and panel is genuinely hotter, small extra bonus
    if action == 1 and panel_delta > 0:
        reward += BETA * min(panel_delta, 10.0)  # cap to avoid runaway

    # Running cost
    if action == 1:
        reward -= GAMMA

    # Switching penalty (chatter)
    switched = (action != last_action)
    if switched:
        if last_switch_time is not None:
            dt = (now.timestamp() - last_switch_time)
            # Heavier penalty for very fast toggles
            if dt < 10:
                reward -= DELTA * 2.0
            elif dt < 30:
                reward -= DELTA
        # update switch timestamp
        last_switch_time = now.timestamp()

    # Safety penalties
    if tank_temp > TANK_MAX_C:
        reward -= LAMBDA_HOT
    if tank_temp < TANK_MIN_C:
        reward -= LAMBDA_COLD

    # Update prev tank temp AFTER computing reward
    prev_tank_temp = tank_temp
    last_action = action

    return reward


# Weather API
API_KEY = "YOUR_OPENWEATHERMAP_KEY"
LAT = "YOUR_LAT"
LON = "YOUR_LON"

def get_weather_data():
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={API_KEY}&units=metric"
    try:
        data = requests.get(url).json()
        cloud_cover = data["clouds"]["all"]
        temp_outside = data["main"]["temp"]
        sunrise = datetime.datetime.fromtimestamp(data["sys"]["sunrise"])
        sunset = datetime.datetime.fromtimestamp(data["sys"]["sunset"])
        now = datetime.datetime.now()
        is_day = 1 if sunrise < now < sunset else 0
        return {
            "cloud_cover": cloud_cover,
            "temp_outside": temp_outside,
            "is_day": is_day,
            "sunrise": sunrise,
            "sunset": sunset,
        }
    except Exception as e:
        print(f"[⚠️] Weather fetch failed: {e}")
        return {"cloud_cover": 50, "is_day": 1}

# MQTT Callbacks
last_msg_time = None

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[✅] Connected to MQTT Broker!")
        client.subscribe(MQTT_TOPIC_SENSOR)
    else:
        print(f"[❌] Connection failed with code {rc}")


def on_message(client, userdata, msg):
    global last_msg_time, tank_temp_history
    last_msg_time = datetime.datetime.now()
    payload = msg.payload.decode("utf-8")
    print(f"[📩] Received: {payload}")
    try:
        temp_in, temp_out, tank_temp = map(float, payload.split(","))
        weather = get_weather_data()
        state = get_state(temp_in, temp_out, tank_temp, weather)
        action = decide_action(state)

        def enforce_guardrails(action):
        """Prevent rapid toggling: honor MIN_ON_TIME and MIN_OFF_TIME."""
        global last_action, last_switch_time
        now_ts = time.time()
        if last_switch_time is None:
            return action
        elapsed = now_ts - last_switch_time
        # If currently ON, require MIN_ON_TIME before turning OFF
        if last_action == 1 and action == 0 and elapsed < MIN_ON_TIME_S:
            return 1
        # If currently OFF, require MIN_OFF_TIME before turning ON
        if last_action == 0 and action == 1 and elapsed < MIN_OFF_TIME_S:
            return 0
        return action

        reward = calculate_reward(temp_in, temp_out, tank_temp, action, weather)
        next_state = state
        update_q_table(state, action, reward, next_state)
        control_msg = "ON" if action == 1 else "OFF"
        client.publish(MQTT_TOPIC_CONTROL, control_msg)
        print(f"[🚀] Pump {control_msg} (Reward: {reward}) | Last Msg: {last_msg_time}")
        tank_temp_history.append(tank_temp)
        if len(tank_temp_history) > 100:
            tank_temp_history.pop(0)
        if len(tank_temp_history) % 50 == 0:
            plt.plot(tank_temp_history)
            plt.show()
    except Exception as e:
        print(f"[❌] Processing error: {e}")
    save_q_table()

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
print("[🔄] Connecting to MQTT broker...")
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_forever()
