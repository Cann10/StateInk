"""Regenerate deterministic recognition fixtures; not used by the recognizer."""
from pathlib import Path
import json
import cv2
import numpy as np

ROOT = Path(__file__).parent
OUTPUT = ROOT


def canvas(): return np.full((500, 800, 3), 255, np.uint8)


def state(image, center, label, rectangle=False):
    if rectangle: cv2.rectangle(image, (center[0]-75, center[1]-42), (center[0]+75, center[1]+42), (0,0,0), 4)
    else: cv2.ellipse(image, center, (72, 46), 0, 0, 360, (0,0,0), 4)
    cv2.putText(image, label, (center[0]-38, center[1]+8), cv2.FONT_HERSHEY_SIMPLEX, .65, (0,0,0), 2)


def arrow(image, start, end, label):
    cv2.arrowedLine(image, start, end, (0,0,0), 4, tipLength=.12)
    cv2.putText(image, label, ((start[0]+end[0])//2-20, (start[1]+end[1])//2-12), cv2.FONT_HERSHEY_SIMPLEX, .55, (0,0,0), 2)


def save(name, image, state_labels, event_labels):
    cv2.imwrite(str(OUTPUT / f"{name}.png"), image)
    connections = [[f"state-{index + 1}", f"state-{index + 2}"] for index in range(len(event_labels))]
    (OUTPUT / f"{name}.expected.json").write_text(json.dumps({"states": len(state_labels), "transitions": len(event_labels), "state_labels": state_labels, "event_labels": event_labels, "connections": connections}, indent=2), encoding="utf-8")


def generate_fixtures(output: Path = ROOT) -> None:
    global OUTPUT
    OUTPUT = output
    OUTPUT.mkdir(parents=True, exist_ok=True)
    image=canvas(); state(image,(180,250),'IDLE'); state(image,(610,250),'RUN'); arrow(image,(255,250),(530,250),'go'); save('simple_two_state',image,['IDLE','RUN'],['go'])
    image=canvas(); centers=[(110,250),(310,250),(510,250),(700,250)]; [state(image,c,n,True) for c,n in zip(centers,['WAIT','PAID','PICK','OUT'])]; [arrow(image,(centers[i][0]+77,250),(centers[i+1][0]-77,250),e) for i,e in enumerate(['coin','select','disp'])]; save('vending_machine_clean',image,['WAIT','PAID','PICK','OUT'],['coin','select','disp'])
    image=canvas(); centers=[(120,250),(390,250),(670,250)]; [state(image,c,n) for c,n in zip(centers,['WAIT','PAID','SOLD'])]; arrow(image,(195,250),(315,250),'coin'); arrow(image,(465,250),(595,250),'sold'); save('vending_machine_broken',image,['WAIT','PAID','SOLD'],['coin','sold'])
    base=canvas(); state(base,(190,250),'A'); state(base,(610,250),'B'); arrow(base,(265,250),(535,250),'next'); matrix=cv2.getRotationMatrix2D((400,250),7,1); image=cv2.warpAffine(base,matrix,(800,500),borderValue=(255,255,255)); save('rotated',image,['A','B'],['next'])
    image=canvas(); state(image,(180,250),'LOW'); state(image,(610,250),'END'); arrow(image,(255,250),(535,250),'go'); image=cv2.GaussianBlur(image,(9,9),3); noise=np.random.default_rng(22).normal(0,12,image.shape).astype(np.int16); image=np.clip(image.astype(np.int16)+noise,0,255).astype(np.uint8); save('low_quality',image,['LOW','END'],['go'])


if __name__ == "__main__":
    generate_fixtures()
