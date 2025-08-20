import csv
from simulator import SolarHeaterSim
from rl_logic import decide_action, update_q_table

def run_simulation(episodes=1):
    for ep in range(episodes):
        sim = SolarHeaterSim()
        state = None
        total_reward, runtime = 0, 0
        csv_file = f"logs/sim_day_{ep+1}.csv"

        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["time","tank_temp","temp_in","temp_out","action","reward","sun_factor","cloud_cover"])
            writer.writeheader()

            done = False
            while not done:
                action = decide_action(state) if state else 0
                new_state, reward, done, info = sim.step_env(action)
                update_q_table(state, action, reward, new_state) if state else None
                state = new_state

                total_reward += reward
                if action == 1:
                    runtime += 1

                writer.writerow(info)

        print(f"[Episode {ep+1}] Final Tank Temp: {info['tank_temp']:.2f}°C | Reward: {total_reward:.2f} | Pump runtime steps: {runtime}")

if __name__ == "__main__":
    run_simulation(episodes=3)
