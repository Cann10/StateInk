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


def save(name, image, state_labels, event_labels, connections=None, category="synthetic"):
    cv2.imwrite(str(OUTPUT / f"{name}.png"), image)
    connections = connections or [[f"state-{index + 1}", f"state-{index + 2}"] for index in range(len(event_labels))]
    (OUTPUT / f"{name}.expected.json").write_text(json.dumps({"category": category, "states": len(state_labels), "transitions": len(event_labels), "state_labels": state_labels, "event_labels": event_labels, "connections": connections}, indent=2), encoding="utf-8")


def generate_fixtures(output: Path = ROOT) -> None:
    global OUTPUT
    OUTPUT = output
    OUTPUT.mkdir(parents=True, exist_ok=True)
    image=canvas(); state(image,(180,250),'IDLE'); state(image,(610,250),'RUN'); arrow(image,(255,250),(530,250),'go'); save('simple_two_state',image,['IDLE','RUN'],['go'])
    image=canvas(); centers=[(110,250),(310,250),(510,250),(700,250)]; [state(image,c,n,True) for c,n in zip(centers,['WAIT','PAID','PICK','OUT'])]; [arrow(image,(centers[i][0]+77,250),(centers[i+1][0]-77,250),e) for i,e in enumerate(['coin','select','disp'])]; save('vending_machine_clean',image,['WAIT','PAID','PICK','OUT'],['coin','select','disp'])
    image=canvas(); centers=[(120,250),(390,250),(670,250)]; [state(image,c,n) for c,n in zip(centers,['WAIT','PAID','SOLD'])]; arrow(image,(195,250),(315,250),'coin'); arrow(image,(465,250),(595,250),'sold'); save('vending_machine_broken',image,['WAIT','PAID','SOLD'],['coin','sold'])
    base=canvas(); state(base,(190,250),'A'); state(base,(610,250),'B'); arrow(base,(265,250),(535,250),'next'); matrix=cv2.getRotationMatrix2D((400,250),7,1); image=cv2.warpAffine(base,matrix,(800,500),borderValue=(255,255,255)); save('rotated',image,['A','B'],['next'])
    image=canvas(); state(image,(180,250),'LOW'); state(image,(610,250),'END'); arrow(image,(255,250),(535,250),'go'); image=cv2.GaussianBlur(image,(9,9),3); noise=np.random.default_rng(22).normal(0,12,image.shape).astype(np.int16); image=np.clip(image.astype(np.int16)+noise,0,255).astype(np.uint8); save('low_quality',image,['LOW','END'],['go'])

    # Camera-like capture: paper boundary, perspective, uneven illumination,
    # mild blur, and sensor noise. Geometry is still deterministic.
    paper=np.full((390,680,3),248,np.uint8)
    cv2.rectangle(paper,(2,2),(677,387),(185,185,185),3)
    state(paper,(155,195),'待機'); state(paper,(525,195),'RUN')
    arrow(paper,(230,195),(450,195),'start')
    target=np.asarray([[68,55],[742,18],[770,464],[32,430]],np.float32)
    source=np.asarray([[0,0],[679,0],[679,389],[0,389]],np.float32)
    matrix=cv2.getPerspectiveTransform(source,target)
    image=np.full((500,800,3),72,np.uint8)
    warped=cv2.warpPerspective(paper,matrix,(800,500),borderValue=(72,72,72))
    mask=cv2.warpPerspective(np.full(paper.shape[:2],255,np.uint8),matrix,(800,500))
    image[mask>0]=warped[mask>0]
    gradient=np.tile(np.linspace(1.0,.72,800,dtype=np.float32),(500,1))[:,:,None]
    image=np.clip(image.astype(np.float32)*gradient,0,255).astype(np.uint8)
    image=cv2.GaussianBlur(image,(3,3),.7)
    noise=np.random.default_rng(31).normal(0,3,image.shape).astype(np.int16)
    image=np.clip(image.astype(np.int16)+noise,0,255).astype(np.uint8)
    save('photo_perspective_shadow',image,['待機','RUN'],['start'],category='photo_like')

    # Curved shaft plus a soft cast shadow; the direction remains reviewable
    # when the V-shaped head is not sufficiently clear.
    image=canvas(); state(image,(170,270),'A'); state(image,(630,230),'B')
    curve=np.asarray([[242,262],[320,190],[430,176],[558,220]],np.int32)
    cv2.polylines(image,[curve],False,(0,0,0),4,cv2.LINE_AA)
    cv2.line(image,(558,220),(535,201),(0,0,0),4,cv2.LINE_AA)
    cv2.line(image,(558,220),(529,231),(0,0,0),4,cv2.LINE_AA)
    cv2.putText(image,'curve', (365,158), cv2.FONT_HERSHEY_SIMPLEX,.55,(0,0,0),2)
    shadow=np.zeros(image.shape[:2],np.uint8); cv2.ellipse(shadow,(410,290),(235,58),-8,0,360,125,-1)
    image=np.clip(image.astype(np.int16)-shadow[:,:,None]//3,0,255).astype(np.uint8)
    save('curved_shadow',image,['A','B'],['curve'],category='photo_like')


if __name__ == "__main__":
    generate_fixtures()
