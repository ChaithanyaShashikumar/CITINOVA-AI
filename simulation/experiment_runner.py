
import os
import sys
import csv
import traci

# --------------------------------------------------
# SUMO CONFIGURATION
# --------------------------------------------------

SUMO_HOME = r"C:\Program Files (x86)\SUMO"
sys.path.append(os.path.join(SUMO_HOME, "tools"))

SUMO_BINARY = os.path.join(SUMO_HOME, "bin", "sumo.exe")

NETWORK_FILE = os.path.join("simulation", "cross.net.xml")
ROUTE_FILE = os.path.join("simulation", "cross.rou.xml")

RESULTS_DIR = "results"
MAX_SIMULATION_STEPS = 2000

DIRECTIONS = {
    "N": ["N_C_0", "N_C_1"],
    "S": ["S_C_0", "S_C_1"],
    "E": ["E_C_0", "E_C_1"],
    "W": ["W_C_0", "W_C_1"]
}

MIN_GREEN = 10
MAX_GREEN = 40
YELLOW_DURATION = 3


# --------------------------------------------------
# TRAFFIC DATA COLLECTION
# --------------------------------------------------

def get_traffic_data():

    data = {}

    for direction, lanes in DIRECTIONS.items():

        vehicle_ids = []

        for lane in lanes:
            vehicle_ids.extend(
                traci.lane.getLastStepVehicleIDs(lane)
            )

        data[direction] = {
            "count": len(vehicle_ids),
            "waiting": sum(
                traci.vehicle.getWaitingTime(vehicle_id)
                for vehicle_id in vehicle_ids
            )
        }

    return data


# --------------------------------------------------
# ADAPTIVE PRIORITY CALCULATION
# --------------------------------------------------

def calculate_group_scores(data):

    ns_score = (
        data["N"]["count"] * 0.6
        + data["S"]["count"] * 0.6
        + data["N"]["waiting"] * 0.04
        + data["S"]["waiting"] * 0.04
    )

    ew_score = (
        data["E"]["count"] * 0.6
        + data["W"]["count"] * 0.6
        + data["E"]["waiting"] * 0.04
        + data["W"]["waiting"] * 0.04
    )

    return ns_score, ew_score


# --------------------------------------------------
# SAFE SIGNAL SWITCHING
# --------------------------------------------------

def switch_signal(target_group):

    if target_group == "EW":
        yellow_phase = 1
        green_phase = 2
    else:
        yellow_phase = 3
        green_phase = 0

    # Yellow transition
    traci.trafficlight.setPhase("C", yellow_phase)

    for _ in range(YELLOW_DURATION):

        if traci.simulation.getMinExpectedNumber() <= 0:
            return False

        traci.simulationStep()

    # Activate the next green phase
    traci.trafficlight.setPhase("C", green_phase)

    return True


# --------------------------------------------------
# RUN EXPERIMENT
# --------------------------------------------------

def run_experiment(mode):

    is_adaptive = mode == "adaptive"

    result_file = os.path.join(
        RESULTS_DIR,
        f"{mode}_results.csv"
    )

    command = [
        SUMO_BINARY,
        "-n", NETWORK_FILE,
        "-r", ROUTE_FILE,
        "--seed", "42",
        "--no-step-log", "true"
    ]

    print(f"\nStarting {mode.upper()} experiment...")

    traci.start(command)

    departure_times = {}
    vehicle_wait_totals = {}

    completed_travel_times = []
    completed_waiting_times = []

    simulation_steps = 0
    total_vehicle_steps = 0

    current_group = "NS"
    green_start_time = 0

    try:

        while (
            traci.simulation.getMinExpectedNumber() > 0
            and simulation_steps < MAX_SIMULATION_STEPS
        ):

            traci.simulationStep()
            simulation_steps += 1

            current_time = traci.simulation.getTime()
            delta_t = traci.simulation.getDeltaT()

            # Record newly departed vehicles
            for vehicle_id in traci.simulation.getDepartedIDList():

                departure_times[vehicle_id] = current_time
                vehicle_wait_totals[vehicle_id] = 0

            # Measure stopped time
            for vehicle_id in traci.vehicle.getIDList():

                total_vehicle_steps += 1

                if traci.vehicle.getSpeed(vehicle_id) < 0.1:

                    vehicle_wait_totals[vehicle_id] += delta_t

            # Record completed journeys
            for vehicle_id in traci.simulation.getArrivedIDList():

                if vehicle_id in departure_times:

                    travel_time = (
                        current_time - departure_times[vehicle_id]
                    )

                    waiting_time = vehicle_wait_totals.get(
                        vehicle_id, 0
                    )

                    completed_travel_times.append(travel_time)
                    completed_waiting_times.append(waiting_time)

                    del departure_times[vehicle_id]
                    vehicle_wait_totals.pop(vehicle_id, None)

            # Adaptive traffic signal control
            if is_adaptive:

                elapsed_green = current_time - green_start_time

                if elapsed_green >= MIN_GREEN:

                    traffic_data = get_traffic_data()

                    ns_score, ew_score = calculate_group_scores(
                        traffic_data
                    )

                    current_score = (
                        ns_score if current_group == "NS"
                        else ew_score
                    )

                    other_score = (
                        ew_score if current_group == "NS"
                        else ns_score
                    )

                    should_switch = (
                        other_score > current_score
                        or elapsed_green >= MAX_GREEN
                    )

                    if should_switch:

                        next_group = (
                            "EW" if current_group == "NS"
                            else "NS"
                        )

                        print(
                            f"{current_time:.0f}s: "
                            f"{current_group} -> {next_group} | "
                            f"NS={ns_score:.2f}, "
                            f"EW={ew_score:.2f}"
                        )

                        switched = switch_signal(next_group)

                        if not switched:
                            break

                        current_group = next_group
                        green_start_time = traci.simulation.getTime()

        # Diagnostics before closing SUMO
        remaining_vehicles = traci.vehicle.getIDCount()
        expected_vehicles = traci.simulation.getMinExpectedNumber()

        print("\nSIMULATION DIAGNOSTICS")
        print("Vehicles completed:", len(completed_travel_times))
        print("Vehicles still in network:", remaining_vehicles)
        print("Vehicles expected:", expected_vehicles)
        print("Vehicles with recorded departures:", len(departure_times))

    finally:
        traci.close()

    # --------------------------------------------------
    # CALCULATE RESULTS
    # --------------------------------------------------

    average_waiting = (
        sum(completed_waiting_times) / len(completed_waiting_times)
        if completed_waiting_times else 0
    )

    average_travel = (
        sum(completed_travel_times) / len(completed_travel_times)
        if completed_travel_times else 0
    )

    results = {
        "experiment": mode,
        "vehicles_completed": len(completed_travel_times),
        "average_waiting_time_seconds": round(average_waiting, 2),
        "average_travel_time_seconds": round(average_travel, 2),
        "total_waiting_time_seconds": round(
            sum(completed_waiting_times), 2
        ),
        "simulation_steps": simulation_steps,
        "vehicle_step_observations": total_vehicle_steps
    }

    # Save CSV
    os.makedirs(RESULTS_DIR, exist_ok=True)

    with open(result_file, "w", newline="") as file:

        writer = csv.DictWriter(
            file,
            fieldnames=results.keys()
        )

        writer.writeheader()
        writer.writerow(results)

    print(f"\n{mode.upper()} EXPERIMENT RESULTS")

    for key, value in results.items():
        print(f"{key}: {value}")

    print("\nResults saved to:", result_file)

    return results


# --------------------------------------------------
# MAIN
# --------------------------------------------------

if __name__ == "__main__":

    run_experiment("adaptive")
