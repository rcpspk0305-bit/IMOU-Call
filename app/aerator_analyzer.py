import logging
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional

# Lazy import cv2 and numpy to avoid loading in contexts where they aren't needed instantly
# but since it's local we will import it inside functions or at top.
try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

logger = logging.getLogger(__name__)

def is_night_time() -> bool:
    """
    Checks if the current local time in India Standard Time (IST, UTC+5:30)
    is within the night shift window (18:00 to 06:00).
    """
    # Resolve UTC time
    utc_now = datetime.now(timezone.utc)
    # Adjust offset to IST (UTC + 5:30)
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    ist_now = utc_now.astimezone(ist_tz)
    
    current_hour = ist_now.hour
    is_night = current_hour >= 18 or current_hour < 6
    logger.debug("Night check (IST hour: %d): %s", current_hour, is_night)
    return is_night

def analyze_motion(frame1_bytes: bytes, frame2_bytes: bytes, roi: Optional[Tuple[int, int, int, int]] = None, threshold: float = 1.5) -> Tuple[float, str]:
    """
    Analyzes motion between two frame images using Dense Optical Flow (Farneback).
    
    :param frame1_bytes: JPEG/PNG image bytes for frame 1.
    :param frame2_bytes: JPEG/PNG image bytes for frame 2.
    :param roi: Cropping bounding box as (y1, y2, x1, x2). None uses the entire frame.
    :param threshold: Motion magnitude threshold separating "WORKING" from "STOPPED".
    :return: Tuple (mean_magnitude, state_string)
    """
    if cv2 is None or np is None:
        logger.error("OpenCV or Numpy are not installed. Cannot analyze motion.")
        return 0.0, "UNKNOWN"

    # Decode frame bytes into numpy array and grayscale
    nparr1 = np.frombuffer(frame1_bytes, np.uint8)
    nparr2 = np.frombuffer(frame2_bytes, np.uint8)
    
    img1 = cv2.imdecode(nparr1, cv2.IMREAD_GRAYSCALE)
    img2 = cv2.imdecode(nparr2, cv2.IMREAD_GRAYSCALE)
    
    if img1 is None or img2 is None:
        logger.error("Failed to decode image bytes into OpenCV grayscales.")
        return 0.0, "UNKNOWN"
        
    # Crop to specific region of interest (ROI) if provided
    if roi:
        try:
            y1, y2, x1, x2 = roi
            # Ensure ROI is within bounds
            h, w = img1.shape
            y1 = max(0, min(y1, h))
            y2 = max(y1, min(y2, h))
            x1 = max(0, min(x1, w))
            x2 = max(x1, min(x2, w))
            if y2 > y1 and x2 > x1:
                img1 = img1[y1:y2, x1:x2]
                img2 = img2[y1:y2, x1:x2]
            else:
                logger.warning("Invalid ROI dimensions: y1=%d, y2=%d, x1=%d, x2=%d. Using full image.", y1, y2, x1, x2)
        except Exception as e:
            logger.error("Error cropping ROI: %s. Using full image.", str(e))

    try:
        # Resize to matching dimensions if there's any discrepancy
        if img1.shape != img2.shape:
            img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

        # Calculate dense optical flow using Farneback's algorithm
        flow = cv2.calcOpticalFlowFarneback(
            prev=img1,
            next=img2,
            flow=None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0
        )
        
        # Calculate optical flow vector magnitude
        magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        mean_magnitude = float(np.mean(magnitude))
        
        state = "WORKING" if mean_magnitude >= threshold else "STOPPED"
        logger.info("Aerator motion analysis complete: mean flow magnitude = %.4f (threshold: %.2f) -> state: %s", mean_magnitude, threshold, state)
        return mean_magnitude, state
    except Exception as e:
        logger.exception("Error during optical flow analysis: %s", str(e))
        return 0.0, "UNKNOWN"
