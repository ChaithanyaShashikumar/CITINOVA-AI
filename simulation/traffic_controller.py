
import os
import sys
import traci

# SUMO installation configuration
SUMO_HOME = r"C:\Program Files (x86)\SUMO"
sys.path.append(os.path.join(SUMO_HOME, "tools"))

# SUMO executable
SUMO_BINARY = os.path.join(SUMO_HOME, "bin", "sumo.exe")

# Simulation configuration
NETWORK_FILE = os.path.join("simulation", "cross.net.xml")
ROUTE_FILE = os.path.join("simulation", "cross.rou.xml")


def run_simulation():

    sumo_command = [
        SUMO_BINARY,
        "-n", NETWORK_FILE,
        "-r", ROUTE_FILE,
        "--end", "120",
        "--no-step-log", "true"
    ]

    print("Starting CITINOVA AI traffic simulation...")

    traci.start(sumo_command)

    try:
        # Traffic light information
        print("Traffic Light IDs:", traci.trafficlight.getIDList())

        print(
            "Current Signal State:",
            traci.trafficlight.getRedYellowGreenState("C")
        )

        print(
            "Current Signal Phase:",
            traci.trafficlight.getPhase("C")
        )

        # Main simulation loop
        while traci.simulation.getMinExpectedNumber() > 0:

            traci.simulationStep()

            simulation_time = traci.simulation.getTime()

            # Vehicle counts in four directions
            north = (
                traci.lane.getLastStepVehicleNumber("N_C_0")
                + traci.lane.getLastStepVehicleNumber("N_C_1")
            )

            south = (
                traci.lane.getLastStepVehicleNumber("S_C_0")
                + traci.lane.getLastStepVehicleNumber("S_C_1")
            )

            east = (
                traci.lane.getLastStepVehicleNumber("E_C_0")
                + traci.lane.getLastStepVehicleNumber("E_C_1")
            )

            west = (
                traci.lane.getLastStepVehicleNumber("W_C_0")
                + traci.lane.getLastStepVehicleNumber("W_C_1")
            )

            # Waiting time in four directions
            north_wait = sum(
                traci.vehicle.getWaitingTime(v)
                for v in (
                    traci.lane.getLastStepVehicleIDs("N_C_0")
                    + traci.lane.getLastStepVehicleIDs("N_C_1")
                )
            )

            south_wait = sum(
                traci.vehicle.getWaitingTime(v)
                for v in (
                    traci.lane.getLastStepVehicleIDs("S_C_0")
                    + traci.lane.getLastStepVehicleIDs("S_C_1")
                )
            )

            east_wait = sum(
                traci.vehicle.getWaitingTime(v)
                for v in (
                    traci.lane.getLastStepVehicleIDs("E_C_0")
                    + traci.lane.getLastStepVehicleIDs("E_C_1")
                )
            )

            west_wait = sum(
                traci.vehicle.getWaitingTime(v)
                for v in (
                    traci.lane.getLastStepVehicleIDs("W_C_0")
                    + traci.lane.getLastStepVehicleIDs("W_C_1")
                )
            )

            total_vehicles = traci.vehicle.getIDCount()

            # Display traffic information every 10 seconds
            if int(simulation_time) % 10 == 0:

                print(
                    f"\nTime: {simulation_time:.0f}s | "
                    f"Vehicles: {total_vehicles}"
                )

                print(
                    f"Vehicle Count -> "
                    f"North: {north} | South: {south} | "
                    f"East: {east} | West: {west}"
                )

                print(
                    f"Waiting Time -> "
                    f"North: {north_wait:.1f}s | "
                    f"South: {south_wait:.1f}s | "
                    f"East: {east_wait:.1f}s | "
                    f"West: {west_wait:.1f}s"
                )

    finally:
        traci.close()

    print("\nCITINOVA AI simulation completed successfully!")


if __name__ == "__main__":
    run_simulation()
