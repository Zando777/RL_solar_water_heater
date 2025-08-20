# RL_solar_water_heater
Personal project to explore the use of Q-learning, weather API, and a MQTT server to intelligently control a solar hot water pump. Very much a WIP and is waiting long term deployment.

File explainations:

main.py - Incomplete 

Core Functionality:
  -Connects to MQTT broker to receive sensor data (panel in/out temps, tank temp)
  -Uses Q-learning to decide when to turn pump ON/OFF
  -Publishes pump control commands back via MQTT
  -Integrates weather data (cloud cover, sunrise/sunset) for better decisions
Key Features:
  -Learns optimal pump control strategy to maximize solar heat capture
  -Balances energy collection with pump operation costs
  -Prevents temperature extremes and equipment damage
  -Adapts to daily/weather patterns through state representation
Learning Objectives:
  -Reward increases when tank temperature rises during sunlight
  -Penalizes excessive pump switching and operation
  -Penalizes unsafe temperature conditions
  
train_sim.py - calls into SolarHeaterSim (digital twin) and runs the RL loop - This mirrors what main.py does with MQTT, but all in software:

-Steps environment
-Chooses an action (decide_action)
-Calculates reward (calculate_reward)
-Updates Q-table (update_q_table)
-Logs results to CSV

mega_sensors_relay.ino - reads temp sensor values, turns on and off pump relay based on esp32 coms

esp32_mqtt_bridge.ino - functions as a bridge from computer processing the RL and the arduino doing the I/O


