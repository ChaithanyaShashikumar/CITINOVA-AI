
from pathlib import Path
import cv2
from ultralytics import YOLO
import json
import time

BASE_DIR = Path(__file__).resolve().parent.parent
VIDEO_PATH = BASE_DIR / "data" / "videos" / "traffic_sample.webm"
OUTPUT_DIR = BASE_DIR / "results" / "vehicle_detection"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_VIDEO = OUTPUT_DIR / "detected_traffic.mp4"
OUTPUT_JSON = OUTPUT_DIR / "traffic_statistics.json"

# COCO classes: car, motorcycle, bus, truck
VEHICLE_CLASSES = [2, 3, 5, 7]
CLASS_NAMES = {
    2: "Car",
    3: "Motorcycle",
    5: "Bus",
    7: "Truck"
}

def main():
    if not VIDEO_PATH.exists():
        print("ERROR: Traffic video not found:", VIDEO_PATH)
        return

    print("Loading YOLO model...")
    model = YOLO("yolo11n.pt")

    cap = cv2.VideoCapture(str(VIDEO_PATH))

    if not cap.isOpened():
        print("ERROR: Cannot open traffic video.")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if fps <= 0:
        fps = 25

    output_fps = min(fps, 15)

    writer = cv2.VideoWriter(
        str(OUTPUT_VIDEO),
        cv2.VideoWriter_fourcc(*"mp4v"),
        output_fps,
        (width, height)
    )

    if not writer.isOpened():
        print("ERROR: Cannot create output video.")
        cap.release()
        return

    totals = {name: 0 for name in CLASS_NAMES.values()}
    frames_processed = 0
    total_detections = 0

    print("Starting vehicle detection...")
    start = time.time()

    # Process at most 300 frames for the first test
    while frames_processed < min(total_frames, 300):
        success, frame = cap.read()

        if not success:
            break

        results = model.predict(
            frame,
            imgsz=640,
            conf=0.35,
            classes=VEHICLE_CLASSES,
            device="cpu",
            verbose=False
        )

        result = results[0]
        annotated = result.plot()

        frame_counts = {name: 0 for name in CLASS_NAMES.values()}

        if result.boxes is not None:
            for cls in result.boxes.cls.tolist():
                class_id = int(cls)
                name = CLASS_NAMES.get(class_id)

                if name:
                    frame_counts[name] += 1
                    totals[name] += 1
                    total_detections += 1

        density = sum(frame_counts.values())

        cv2.putText(
            annotated,
            f"Vehicles in frame: {density}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 255, 0),
            2
        )

        writer.write(annotated)
        frames_processed += 1

        if frames_processed % 25 == 0:
            print(f"Processed {frames_processed} frames...")

    cap.release()
    writer.release()

    elapsed = time.time() - start

    statistics = {
        "frames_processed": frames_processed,
        "total_detection_instances": total_detections,
        "average_vehicles_per_frame": (
            round(total_detections / frames_processed, 2)
            if frames_processed else 0
        ),
        "class_detection_instances": totals,
        "processing_time_seconds": round(elapsed, 2),
        "note": "Detection instances across frames, not unique vehicles."
    }

    OUTPUT_JSON.write_text(json.dumps(statistics, indent=4))

    print("\n===== CITINOVA AI RESULTS =====")
    print(json.dumps(statistics, indent=4))
    print("\nProcessed video:", OUTPUT_VIDEO)
    print("Statistics:", OUTPUT_JSON)


if __name__ == "__main__":
    main()
