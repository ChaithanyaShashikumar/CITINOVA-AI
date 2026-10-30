
import os
import sys
import traci

# SUMO configuration
SUMO_HOME = r"C:\Program Files (x86)\SUMO"
sys.path.append(os.path.join(SUMO_HOME, "tools"))

SUMO_BINARY = os.path.join(SUMO_HOME, "bin", "sumo-gui.exe")

NETWORK_FILE = os.path.join("simulation", "cross.net.xml")
ROUTE_FILE = os.path.join("simulation", "cross.rou.xml")

TRAFFIC_LIGHT_ID = "C"
AMBULANCE_ID = "ambulance_1"

DIRECTIONS = {
    "North": ["N_C_0", "N_C_1"],
    "South": ["S_C_0", "S_C_1"],
    "East": ["E_C_0", "E_C_1"],
    "West": ["W_C_0", "W_C_1"]
}

MIN_GREEN = 10
MAX_GREEN = 40
YELLOW_DURATION = 3


def get_traffic_data():
    data = {}

    for direction, lanes in DIRECTIONS.items():
        vehicle_ids = []

        for lane in lanes:
            vehicle_ids.extend(
                traci.lane.getLastStepVehicleIDs(lane)
            )

        waiting_time = sum(
            traci.vehicle.getWaitingTime(vehicle_id)
            for vehicle_id in vehicle_ids
        )

        data[direction] = {
            "vehicles": len(vehicle_ids),
            "waiting_time": waiting_time
        }

    return data


def calculate_traffic_scores(data):
    return {
        direction: (
            0.6 * values["vehicles"]
            + 0.4 * values["waiting_time"] / 10
        )
        for direction, values in data.items()
    }


def get_ambulance_direction():
    if AMBULANCE_ID not in traci.vehicle.getIDList():
        return None

    road_id = traci.vehicle.getRoadID(AMBULANCE_ID)

    if road_id == "E_C":
        return "EW"
    elif road_id == "W_C":
        return "EW"
    elif road_id == "N_C":
        return "NS"
    elif road_id == "S_C":
        return "NS"

    return None


def switch_signal(current_group, next_group):
    yellow_phase = 1 if current_group == "NS" else 3

    traci.trafficlight.setPhase(
        TRAFFIC_LIGHT_ID,
        yellow_phase
    )

    for _ in range(YELLOW_DURATION):
        traci.simulationStep()

    green_phase = 0 if next_group == "NS" else 2

    traci.trafficlight.setPhase(
        TRAFFIC_LIGHT_ID,
        green_phase
    )

    print(
        f"Signal changed: {current_group} -> {next_group}"
    )


def run_simulation():
    sumo_command = [
        SUMO_BINARY,
        "-n", NETWORK_FILE,
        "-r", ROUTE_FILE,
        "--no-step-log", "true"
    ]

    print("\n====================================")
    print(" CITINOVA AI TRAFFIC CONTROL SYSTEM")
    print(" Adaptive Signals + Ambulance Priority")
    print("====================================\n")

    traci.start(sumo_command)

    try:
        print("Traffic lights:", traci.trafficlight.getIDList())

        current_group = "NS"
        green_start_time = 0
        emergency_active = False
        ambulance_cleared = False

        while traci.simulation.getMinExpectedNumber() > 0:

            traci.simulationStep()

            current_time = traci.simulation.getTime()

            data = get_traffic_data()
            scores = calculate_traffic_scores(data)

            ns_score = scores["North"] + scores["South"]
            ew_score = scores["East"] + scores["West"]

            ambulance_direction = get_ambulance_direction()

            # Emergency vehicle priority
            if ambulance_direction and not emergency_active:

                emergency_active = True

                print(
                    f"\nEMERGENCY DETECTED at {current_time:.1f}s"
                )
                print(
                    f"Ambulance direction: {ambulance_direction}"
                )

                if ambulance_direction != current_group:
                    switch_signal(
                        current_group,
                        ambulance_direction
                    )

                current_group = ambulance_direction
                green_start_time = traci.simulation.getTime()

            # Maintain priority until ambulance exits
            if emergency_active:

                if AMBULANCE_ID not in traci.vehicle.getIDList():

                    emergency_active = False
                    ambulance_cleared = True

                    green_start_time = current_time

                    print(
                        f"\nAMBULANCE CLEARED at {current_time:.1f}s"
                    )
                    print("Returning to adaptive traffic control.")

                else:
                    continue

            # Normal adaptive traffic signal control
            elapsed_green = current_time - green_start_time

            if elapsed_green >= MIN_GREEN:

                if current_group == "NS":
                    other_group = "EW"
                    current_score = ns_score
                    other_score = ew_score
                else:
                    other_group = "NS"
                    current_score = ew_score
                    other_score = ns_score

                should_switch = (
                    other_score > current_score
                    or elapsed_green >= MAX_GREEN
                )

                if should_switch:

                    switch_signal(
                        current_group,
                        other_group
                    )

                    current_group = other_group
                    green_start_time = traci.simulation.getTime()

            if int(current_time) % 10 == 0:

                print(f"\nSimulation time: {current_time:.0f}s")

                for direction, values in data.items():
                    print(
                        f"{direction}: "
                        f"{values['vehicles']} vehicles | "
                        f"Waiting: {values['waiting_time']:.1f}s"
                    )

                print("Active signal:", current_group)

    finally:
        traci.close()

    print("\nCITINOVA AI simulation completed!")


if __name__ == "__main__":
    run_simulation()
