import cv2
import numpy as np
import argparse
import sys

def calculate_motion_stats(video_path, roi=None):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video file {video_path}")
        return None

    magnitudes = []
    prev_frame = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Crop to ROI if provided
        if roi:
            y1, y2, x1, x2 = roi
            gray = gray[y1:y2, x1:x2]

        if prev_frame is not None:
            # Match sizes
            if prev_frame.shape != gray.shape:
                gray = cv2.resize(gray, (prev_frame.shape[1], prev_frame.shape[0]))

            flow = cv2.calcOpticalFlowFarneback(
                prev=prev_frame,
                next=gray,
                flow=None,
                pyr_scale=0.5,
                levels=3,
                winsize=15,
                iterations=3,
                poly_n=5,
                poly_sigma=1.2,
                flags=0
            )
            magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            mean_mag = np.mean(magnitude)
            magnitudes.append(mean_mag)

        prev_frame = gray

    cap.release()

    if not magnitudes:
        return None

    mean = np.mean(magnitudes)
    std = np.std(magnitudes)
    variance_coef = std / mean if mean > 0 else 0.0
    return {
        "mean_magnitude": mean,
        "std_magnitude": std,
        "variance_coefficient": variance_coef,
        "min_magnitude": np.min(magnitudes),
        "max_magnitude": np.max(magnitudes)
    }

def main():
    parser = argparse.ArgumentParser(description="Lightweight training utility to establish aerator baseline threshold.")
    parser.add_argument("--working", type=str, required=True, help="Path to video of working aerator.")
    parser.add_argument("--non_working", type=str, required=True, help="Path to video of non-working aerator.")
    parser.add_argument("--roi", type=str, default=None, help="Region of interest as y1,y2,x1,x2")

    args = parser.parse_args()
    
    roi = None
    if args.roi:
        try:
            roi = tuple(map(int, args.roi.split(",")))
        except ValueError:
            print("Error: ROI must be formatted as y1,y2,x1,x2")
            sys.exit(1)

    print("Analyzing working aerator video...")
    working_stats = calculate_motion_stats(args.working, roi)
    
    print("\nAnalyzing non-working aerator video...")
    non_working_stats = calculate_motion_stats(args.non_working, roi)

    if not working_stats or not non_working_stats:
        print("\nError: Could not calculate statistics for one or both videos.")
        sys.exit(1)

    print("\n" + "="*50)
    print("AERATOR MOTION ANALYSIS RESULTS")
    print("="*50)
    print("WORKING VIDEO STATS:")
    for k, v in working_stats.items():
        print(f"  {k:25}: {v:.4f}")
    print("\nNON-WORKING VIDEO STATS:")
    for k, v in non_working_stats.items():
        print(f"  {k:25}: {v:.4f}")

    # Establish baseline threshold
    suggested_threshold = (working_stats["mean_magnitude"] + non_working_stats["mean_magnitude"]) / 2.0
    print("\n" + "="*50)
    print(f"SUGGESTED MOTION THRESHOLD: {suggested_threshold:.4f}")
    print("="*50)

if __name__ == "__main__":
    main()
