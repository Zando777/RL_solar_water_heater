import csv, random, datetime, math, time

class SolarHeaterSim:
    def __init__(self, start_time=None, step_minutes=1):
        self.time = start_time or datetime.datetime.now().replace(hour=6, minute=0, second=0, microsecond=0)
        self.step = datetime.timedelta(minutes=step_minutes)

        # System state
        self.tank_temp = 40.0  # initial water temp (°C)
        self.ambient_temp = 20.0
        self.temp_in = self.ambient_temp
        self.temp_out = self.ambient_temp
        self.cloud_cover = 0.2   # fraction [0–1]

        # Panel/tank dynamics
        self.tank_loss_rate = 0.02   # °C per step lost to environment
        self.panel_gain_max = 15.0   # max panel delta over ambient on clear noon
        self.tank_gain_rate = 0.1    # °C per step transferred when pump ON

    def solar_irradiance(self):
        """Returns a normalized solar factor 0..1 based on time of day and cloud cover."""
        hr = self.time.hour + self.time.minute/60.0
        # bell-shaped irradiance (sunrise 6, peak noon, sunset 18)
        solar = max(0.0, math.sin(math.pi * (hr - 6) / 12))
        # clouds reduce irradiance
        solar *= (1 - self.cloud_cover)
        return solar

    def update_weather(self):
        """Random cloud cover changes slowly."""
        self.cloud_cover = min(1.0, max(0.0, self.cloud_cover + random.uniform(-0.05, 0.05)))

    def step_env(self, action):
        """
        Take one simulation step given action (0=OFF, 1=ON).
        Returns: new_state, reward, done, info
        """
        solar = self.solar_irradiance()
        self.update_weather()

        # Update panel temps (simple model: ambient + solar heating)
        self.temp_in = self.ambient_temp
        self.temp_out = self.ambient_temp + self.panel_gain_max * solar

        # Tank loses heat naturally
        self.tank_temp -= self.tank_loss_rate

        # If pump ON and panel is hotter, transfer heat
        if action == 1 and self.temp_out > self.tank_temp:
            delta = (self.temp_out - self.tank_temp) * self.tank_gain_rate
            self.tank_temp += delta

        # Calculate reward (reuse your RL reward function!)
        from rl_logic import calculate_reward, get_state  # import your RL functions
        weather = {
            "cloud_cover": int(self.cloud_cover * 100),
            "sunrise": self.time.replace(hour=6, minute=0),
            "sunset": self.time.replace(hour=18, minute=0)
        }
        state = get_state(self.temp_in, self.temp_out, self.tank_temp, weather)
        reward = calculate_reward(self.temp_in, self.temp_out, self.tank_temp, action, weather)

        # Advance time
        self.time += self.step
        done = (self.time.hour >= 20)  # end sim at 20:00

        info = {
            "time": self.time,
            "sun_factor": solar,
            "cloud_cover": self.cloud_cover,
            "tank_temp": self.tank_temp,
            "temp_in": self.temp_in,
            "temp_out": self.temp_out,
            "action": action,
            "reward": reward
        }

        return state, reward, done, info
