"""Generate the tutorial diagrams (draw.io) used in the README, in a brand theme.

Recreates the diagrams of the original Mayurji/MLOps-Project tutorial, adapted
to this lab: Docker Compose instead of Kubernetes, the airport use case and
the real component names, topics and ports.

    uv run --no-project python docs/diagrams/generate_tutorial.py [--brand aurora|majlisofai] [--out DIR]
    make diagrams BRAND=aurora                                       # + exports PNG
"""

from pathlib import Path
from xml.sax.saxutils import quoteattr

import brand

TH, OUT = brand.cli(Path(__file__).resolve().parents[1] / "images")

SKETCH = "sketch=1;curveFitting=1;jiggle=2;" if TH.sketch else ""
BASE = f"html=1;whiteSpace=wrap;{SKETCH}{brand.font(TH)}fontColor={TH.text};"
ROUND = brand.rounded(TH)
NODE = f"{BASE}{ROUND}fillColor={TH.node.fill};strokeColor={TH.node.stroke};strokeWidth={TH.node.width};"
ZONE = f"{BASE}{ROUND}fillColor={TH.zone.fill};strokeColor={TH.zone.stroke};strokeWidth={TH.node.width};"
OUTLINE = f"{BASE}{ROUND}fillColor=none;strokeColor={TH.group_stroke};strokeWidth={TH.node.width};"
ACCENT = (f"{BASE}{ROUND}fillColor={TH.accent.fill};strokeColor={TH.accent.stroke};fontColor={TH.accent.text};"
          f"strokeWidth={TH.node.width};")
STREAM = f"strokeColor={TH.stream};fontColor={TH.stream};"
TOP = "verticalAlign=top;spacingTop=8;"
TOP_LEFT = "verticalAlign=top;align=left;spacingLeft=14;spacingTop=8;"

STYLES = {
    "box": f"{NODE}fontSize=16;",
    "dashed": f"{NODE}dashed=1;fontSize=15;",
    "dashed_fill": f"{NODE}dashed=1;fontSize=16;",
    "group": f"{OUTLINE}fontSize=16;{TOP}",
    "group_fill": f"{ZONE}fontSize=17;{TOP}",
    "group_dashed": f"{OUTLINE}dashed=1;fontSize=16;{TOP_LEFT}",
    "group_dashed_fill": f"{ZONE}dashed=1;fontSize=17;{TOP}",
    "white": f"{NODE}fontSize=16;",
    "blue": f"{NODE}{STREAM}fontSize=16;",
    "blue_group": f"{OUTLINE}dashed=1;{STREAM}fontSize=16;{TOP_LEFT}spacingLeft=16;spacingTop=10;fontStyle=1;",
    "pill": f"{ACCENT}fontSize=15;",
    "lavender": f"{ACCENT}fontSize=15;",
    "text": f"text;{BASE}align=center;verticalAlign=middle;fontSize=16;",
    "text_left": f"text;{BASE}align=left;verticalAlign=top;fontSize=15;fontColor={TH.muted};",
    "title": f"text;{BASE}align=left;verticalAlign=middle;fontSize=20;fontStyle=1;",
    "note_blue": f"text;{BASE}align=left;verticalAlign=top;fontSize=15;fontColor={TH.stream};",
    "note_orange": f"text;{BASE}align=left;verticalAlign=top;fontSize=15;fontColor={TH.monitor};",
    "dot_blue": f"{BASE}ellipse;fillColor={TH.stream};strokeColor={TH.stream};",
}

EDGE = (f"{BASE}whiteSpace=nowrap;endArrow=block;endFill=1;endSize=7;strokeWidth=1.5;fontSize=13;"
        f"strokeColor={TH.edge};fontColor={TH.muted};labelBackgroundColor={TH.edge_label_bg};")
EDGES = {
    "arrow": EDGE + "edgeStyle=none;",
    "orth": EDGE + "edgeStyle=orthogonalEdgeStyle;rounded=1;",
    "dashed": EDGE + "edgeStyle=none;dashed=1;",
    "dashed_orth": EDGE + "edgeStyle=orthogonalEdgeStyle;rounded=1;dashed=1;",
    "both": EDGE + "edgeStyle=none;dashed=1;startArrow=block;startFill=1;startSize=7;",
    "blue": EDGE + f"edgeStyle=none;{STREAM}",
    "blue_orth": EDGE + f"edgeStyle=orthogonalEdgeStyle;rounded=1;{STREAM}",
    "dotted": EDGE + "edgeStyle=none;dashed=1;dashPattern=2 4;",
    "orange_orth": EDGE + f"edgeStyle=orthogonalEdgeStyle;rounded=1;strokeColor={TH.monitor};fontColor={TH.monitor};",
}
MONITOR = f"<font color='{TH.monitor}'>"
ALERT = f"strokeColor={TH.alert};fontColor={TH.alert};strokeWidth=2;"


class Diagram:
    def __init__(self, name: str, width: int, height: int) -> None:
        self.name, self.width, self.height = name, width, height
        self.cells: list[str] = []
        self.n = 0

    def box(self, kind: str, label: str, x: int, y: int, w: int = 170, h: int = 80, extra: str = "") -> str:
        self.n += 1
        cid = f"c{self.n}"
        self.cells.append(
            f'<mxCell id="{cid}" value={quoteattr(label)} style={quoteattr(STYLES[kind] + extra)} vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return cid

    def edge(self, kind: str, src: str, tgt: str, label: str = "", points=(), extra: str = "",
             label_pos: float = 0) -> str:
        self.n += 1
        cid = f"c{self.n}"
        pts = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in points)
        geo = f'<mxGeometry x="{label_pos}" relative="1" as="geometry">'
        geometry = geo + (f'<Array as="points">{pts}</Array>' if pts else "") + "</mxGeometry>"
        self.cells.append(
            f'<mxCell id="{cid}" value={quoteattr(label)} style={quoteattr(EDGES[kind] + extra)} edge="1" '
            f'parent="1" source="{src}" target="{tgt}">{geometry}</mxCell>')
        return cid

    def save(self, filename: str) -> None:
        xml = (
            '<mxfile host="drawio" type="device">'
            f'<diagram name={quoteattr(self.name)} id="{filename}">'
            f'<mxGraphModel grid="1" gridSize="10" guides="1" page="1" pageWidth="{self.width}" '
            f'pageHeight="{self.height}" background="{TH.canvas}" math="0" shadow="0"><root>'
            '<mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(self.cells) +
            "</root></mxGraphModel></diagram></mxfile>\n")
        (OUT / filename).write_text(xml)
        print(f"wrote {OUT / filename}")


# side anchors for straight edges
R, L, T, B = "exitX=1;exitY=0.5;", "entryX=0;entryY=0.5;", "exitX=0.5;exitY=0;", "entryX=0.5;entryY=1;"


def airport_analogy() -> None:
    d = Diagram("Step 1 - the airport analogy", 1300, 520)
    d.box("title", "The airport analogy — a security checkpoint for money", 20, 10, 700, 40)
    passenger = d.box("lavender", "Passenger pays<br>'The Traveller'", 30, 80, 230, 64)
    kafka = d.box("lavender", "Kafka<br>'The Security Queue'", 380, 80, 230, 64)
    consumer = d.box("lavender", "Fraud consumer<br>'The Supervisor'", 730, 80, 230, 64)
    api = d.box("lavender", "Scoring API<br>'The Security Officer'", 730, 260, 230, 64)
    mlflow = d.box("lavender", "MLflow @champion<br>'The Security Manual'", 380, 210, 230, 64)
    feast = d.box("lavender", "Feast / Redis<br>'The Traveller's File'", 380, 320, 230, 64)
    app = d.box("pill", "Airport app / analyst", 400, 440, 190, 50)
    auditor = d.box("lavender", "Evidently<br>'The Auditor'", 1050, 80, 220, 64)
    control = d.box("lavender", "Prometheus + Grafana<br>'The Control Room'", 1050, 260, 220, 64)

    d.edge("arrow", passenger, kafka, "sends payment")
    d.edge("arrow", kafka, consumer, "pulls next in line")
    d.edge("arrow", consumer, api, "is this fraud?")
    d.edge("dotted", mlflow, api, "provides the rules")
    d.edge("dotted", feast, api, "provides history")
    d.edge("arrow", app, api, "asks for a prediction", extra="exitX=1;exitY=0.5;entryX=0.5;entryY=1;")
    d.edge("dotted", consumer, auditor, "do travellers still<br>look like the manual?")
    d.edge("dotted", api, control, "watches the counters")
    d.save("tutorial-01-airport-analogy.drawio")


def architecture(filename: str, monitoring: bool) -> None:
    width = 1760 if monitoring else 1350
    title = "Monitoring" if monitoring else "Architecture"
    d = Diagram(f"Lab - {title.lower()}", width, 680)
    d.box("text", "Docker Compose project <b>fraud-lab</b> · one laptop", 390, 8, 920, 34)

    offline = d.box("box", "Feast offline<br>store<br>(parquet)", 20, 300, 150, 100)
    training = d.box("box", "Model<br>training<br>(trainer job)", 210, 250, 130, 230)
    user = d.box("box", "User", 210, 540, 130, 70)

    compose_w = 1340 if monitoring else 920
    d.box("group_fill", "", 380, 50, compose_w, 580)

    d.box("text", "Published ports", 410, 92, 170, 30)
    ports_col = d.box("group", "", 415, 125, 160, 375)
    port_api = d.box("box", "API :8000", 440, 140, 110, 46, "fontSize=15;")
    port_kafka = d.box("box", "Kafka :9094", 440, 280, 110, 46, "fontSize=15;")
    port_mlflow = d.box("box", "MLflow :5001", 440, 420, 110, 46, "fontSize=15;")

    d.box("text", "Containers", 610, 62, 680, 26)
    containers = d.box("group", "", 610, 92, 680, 440)
    api = d.box("dashed", "Scoring API<br>FastAPI", 650, 123, 140, 80)
    consumer_label = (f"Fraud consumer ×N<br>{MONITOR}+ Evidently</font>" if monitoring
                      else "Fraud consumer ×N")
    consumer = d.box("dashed", consumer_label, 880, 123, 170, 80)
    topic = d.box("dashed", "Kafka topic<br>airport.transactions", 880, 263, 170, 80)
    redis = d.box("dashed", "Redis<br>Feast online store", 1110, 263, 150, 80)
    mlflow = d.box("dashed", "MLflow<br>+ Postgres", 650, 403, 140, 80)
    producer = d.box("dashed", "Payment simulator<br>(producer)", 880, 403, 170, 80)
    out_topics = d.box("dashed", "airport.predictions<br>airport.fraud-alerts", 1110, 403, 150, 80, "fontSize=13;")
    d.box("text_left", "6 fields per payment event", 870, 490, 220, 26)
    d.box("text_left", "4 passenger features", 1110, 345, 170, 26)

    d.edge("arrow", offline, training)
    d.edge("arrow", training, port_mlflow, "log runs", extra="exitX=1;exitY=0.82;entryX=0;entryY=0.5;", label_pos=-0.4)
    d.edge("arrow", user, training)
    d.edge("orth", user, ports_col, "localhost", points=[(495, 575)], extra="exitX=1;exitY=0.5;entryX=0.5;entryY=1;")
    d.edge("arrow", port_api, api)
    d.edge("arrow", port_kafka, topic)
    d.edge("arrow", port_mlflow, mlflow)
    d.edge("arrow", mlflow, api, "load @champion", extra=T + B, label_pos=0.45)
    d.edge("arrow", producer, topic, extra=T + B)
    d.edge("arrow", topic, consumer, extra=T + B)
    d.edge("arrow", consumer, api, "/predict", extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
    d.edge("orth", redis, api, "online features", points=[(1185, 108), (720, 108)],
           extra="exitX=0.5;exitY=0;entryX=0.5;entryY=0;", label_pos=-0.75)
    d.edge("orth", consumer, out_topics, points=[(1080, 163), (1080, 443)], extra=R + L)

    if monitoring:
        d.box("group_dashed", f"{MONITOR}Monitoring containers</font>", 1320, 92, 360, 440)
        prom = d.box("box", f"{MONITOR}Prometheus</font><br>+ alert rules", 1375, 150, 140, 80)
        grafana = d.box("box", f"{MONITOR}Grafana</font><br>:3000", 1540, 150, 120, 80)
        exporters = d.box("box", f"{MONITOR}Exporters</font><br>kafka · redis · cAdvisor", 1375, 300, 140, 80,
                          "fontSize=14;")
        alertmanager = d.box("box", f"{MONITOR}Alertmanager</font><br>:9093", 1540, 300, 120, 80)
        d.box("box", f"{MONITOR}Evidently report</font><br>reports/drift_report.html<br>"
              "<i>written by the consumer every 200 txns</i>", 1345, 420, 310, 80, "fontSize=14;")
        d.edge("orange_orth", containers, prom, "scrape<br>/metrics", extra="exitX=1;exitY=0.17;entryX=0;entryY=0.5;")
        d.edge("arrow", prom, grafana)
        d.edge("arrow", exporters, prom, extra=T + B)
        d.edge("arrow", prom, alertmanager, "alerts", extra="exitX=1;exitY=0.8;entryX=0;entryY=0.2;")
    d.save(filename)


def docker_compose() -> None:
    d = Diagram("Step 3 - Docker Compose", 1180, 640)
    trainer = d.box("dashed_fill", "Model training<br><i>docker compose run trainer</i>", 20, 40, 170, 250, "fontSize=15;")
    user = d.box("text", "User", 30, 400, 80, 40)
    d.box("group_dashed_fill", "Docker Compose project · fraud-lab · one laptop", 230, 20, 930, 600)

    d.box("text", "Published ports (host)", 270, 100, 200, 30)
    d.box("group_dashed", "", 280, 130, 180, 420)
    ports = {
        "api": d.box("dashed", "API :8000", 300, 160, 140, 50),
        "mlflow": d.box("dashed", "MLflow :5001", 300, 260, 140, 50),
        "kafka": d.box("dashed", "Kafka :9094", 300, 360, 140, 50),
        "grafana": d.box("dashed", "Grafana :3000", 300, 460, 140, 50),
    }
    d.box("text", "Containers  (service name = DNS name)", 520, 100, 600, 30)
    d.box("group_dashed", "", 510, 130, 620, 420)
    containers = {
        "api": d.box("dashed", "api", 535, 160, 150, 50),
        "mlflow": d.box("dashed", "mlflow", 535, 260, 150, 50),
        "kafka": d.box("dashed", "kafka", 535, 360, 150, 50),
        "grafana": d.box("dashed", "grafana", 535, 460, 150, 50),
    }
    for i, name in enumerate(["redis", "postgres", "kafka-init · kafka-ui", "prometheus"]):
        d.box("dashed", name, 725, 160 + i * 100, 175, 50)
    for i, name in enumerate(["producer", "consumer ×N", "alertmanager", "exporters · cAdvisor"]):
        d.box("dashed", name, 935, 160 + i * 100, 175, 50)
    d.box("text", "inside the network: api:8000 · mlflow:5000 · kafka:9092 · redis:6379", 280, 560, 850, 34,
          "fontSize=15;")

    for name, port in [("api", "8000"), ("mlflow", "5001"), ("kafka", "9094"), ("grafana", "3000")]:
        d.edge("dashed", user, ports[name], port, extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
        d.edge("both", ports[name], containers[name])
    d.edge("dashed_orth", trainer, containers["mlflow"], "runs · models  (mlflow:5000)",
           points=[(495, 78), (495, 235), (610, 235)], extra="exitX=1;exitY=0.15;entryX=0.5;entryY=0;",
           label_pos=-0.55)
    d.save("tutorial-03-docker-compose.drawio")


def feast() -> None:
    d = Diagram("Step 4 - Feast", 1120, 720)
    gen = d.box("white", "Generate data<br><i>DVC: generate</i>", 20, 220, 150, 80)
    parquet = d.box("white", "Parquet files<br><i>DVC: features</i>", 220, 220, 150, 80)
    fst = d.box("white", "Feast<br><i>apply · registry</i>", 440, 70, 150, 70)
    training = d.box("white", "Training<br><i>3 models</i>", 440, 220, 150, 80)
    d.box("text_left", "Historical records<br>(60 days · 72k payments,<br>label is_fraud)", 30, 70, 240, 90)

    redis = d.box("blue", "Redis<br><i>online store</i>", 680, 70, 150, 70)
    d.box("note_blue", "4 passenger features<br>(latest value per passenger)", 680, 8, 260, 56)
    d.box("dot_blue", "", 940, 170, 36, 36)
    d.box("note_blue", "running in<br>Docker Compose", 985, 165, 140, 50)

    d.box("blue_group", "Real-time streaming", 150, 350, 730, 310)
    mlflow = d.box("blue", "MLflow<br>@champion", 440, 395, 150, 70)
    api = d.box("blue", "Scoring API<br>/predict", 680, 395, 150, 70)
    d.box("note_blue", "6 transaction fields per event", 180, 520, 260, 30)
    sim = d.box("blue", "Payment<br>simulator", 190, 565, 150, 70)
    topic = d.box("blue", "Kafka topic<br>airport.transactions", 430, 565, 170, 70, "fontSize=15;")
    consumer = d.box("blue", "Fraud consumer<br>fraud-detector", 680, 565, 150, 70, "fontSize=15;")
    result = d.box("blue", "Prediction result<br>predictions · alerts", 930, 565, 170, 70, "fontSize=15;")
    d.box("note_blue", "model input = 6 fields from the event + 4 passenger features from Feast + 1 derived ratio",
          150, 668, 900, 30)

    d.edge("arrow", gen, parquet)
    d.edge("orth", parquet, fst, extra="exitX=0.5;exitY=0;entryX=0;entryY=0.5;")
    d.edge("arrow", parquet, training, "labels")
    d.edge("arrow", fst, redis, "materialize")
    d.edge("arrow", fst, training, "point-in-time join", extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    d.edge("arrow", training, mlflow, "log + register", extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;strokeWidth=2.5;",
           label_pos=-0.45)
    d.edge("blue", mlflow, api, "load model")
    d.edge("blue_orth", redis, api, "online lookup", points=[(870, 105), (870, 370), (755, 370)],
           extra="exitX=1;exitY=0.5;entryX=0.5;entryY=0;")
    d.edge("blue", sim, topic)
    d.edge("blue", topic, consumer)
    d.edge("blue", consumer, api, "/predict", extra="exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
    d.edge("blue", consumer, result)
    d.save("tutorial-04-feast.drawio")


def train() -> None:
    d = Diagram("Step 5 - Train", 1000, 200)
    gen = d.box("box", "Generate airport<br>payments<br><i>DVC → parquet</i>", 20, 40, 190, 100)
    trn = d.box("box", "Train<br><i>scikit-learn · 3 models</i>", 370, 20, 210, 140)
    mlf = d.box("box", "MLflow<br><i>tracking + registry</i>", 750, 50, 200, 80)
    d.edge("arrow", gen, trn, "Feast point-in-time join")
    d.edge("arrow", trn, mlf, "runs · metrics · model")
    d.save("tutorial-05-train.drawio")


def serve() -> None:
    d = Diagram("Step 7 - Serve", 1000, 340)
    req = d.box("box", "Request<br><i>POST /predict</i>", 20, 40, 170, 80)
    api = d.box("box", "FastAPI<br>/predict", 350, 20, 170, 120)
    out = d.box("box", "Fraud prediction<br><i>p(fraud) · is_fraud</i>", 700, 40, 190, 80)
    mlf = d.box("box", "MLflow<br>@champion", 260, 230, 160, 70)
    fst = d.box("box", "Feast online<br>(Redis)", 450, 230, 160, 70)
    d.edge("arrow", req, api, "airport payment")
    d.edge("arrow", api, out, "JSON")
    d.edge("arrow", mlf, api, "model", extra="exitX=0.5;exitY=0;entryX=0.3;entryY=1;")
    d.edge("arrow", fst, api, "passenger features", extra="exitX=0.5;exitY=0;entryX=0.7;entryY=1;")
    d.save("tutorial-07-serve.drawio")


def kafka() -> None:
    d = Diagram("Step 8 - Kafka", 1180, 480)
    d.box("title", "Event Driven Architecture", 20, 10, 400, 36)
    d.box("text", "Kafka producer", 70, 80, 200, 30)
    sim = d.box("box", "Airport payment<br>simulator", 80, 115, 180, 80)
    d.box("text_left", "In production: payment<br>terminals / POS gateway", 60, 205, 260, 60)
    topic = d.box("box", "Kafka topic<br>airport.transactions", 380, 95, 190, 120)
    d.box("text", "Kafka consumer group  fraud-detector", 640, 60, 340, 30)
    consumer = d.box("box", "Fraud consumers ×N<br><i>one partition each</i>", 680, 95, 260, 120)
    preds = d.box("box", "airport.predictions", 1000, 95, 170, 50, "fontSize=14;")
    alerts = d.box("box", "airport.fraud-alerts", 1000, 165, 170, 50, "fontSize=14;")
    api = d.box("box", "Scoring API<br>/predict", 730, 330, 160, 80)
    mlf = d.box("box", "MLflow<br>@champion", 450, 300, 150, 64)
    fst = d.box("box", "Feast<br>(Redis)", 450, 390, 150, 64)
    d.edge("arrow", sim, topic, "key = passenger_id")
    d.edge("arrow", topic, consumer)
    d.edge("both", consumer, api, "HTTP", extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;dashed=0;")
    d.edge("arrow", mlf, api)
    d.edge("arrow", fst, api)
    d.edge("arrow", consumer, preds, extra="exitX=1;exitY=0.3;entryX=0;entryY=0.5;")
    d.edge("arrow", consumer, alerts, "if fraud", extra="exitX=1;exitY=0.75;entryX=0;entryY=0.5;", label_pos=-0.2)
    d.save("tutorial-08-kafka.drawio")


def automation() -> None:
    d = Diagram("Step 9 - Automate", 1320, 660)
    d.box("title", "Automation with Prefect — run any stage from a UI, retrain nightly and on drift", 20, 8, 1000, 36)
    user = d.box("text", "User", 20, 230, 70, 40)
    console = d.box("box", "Lab console :8090<br><i>live architecture · Run</i>", 120, 90, 210, 80, "fontSize=15;")
    ui = d.box("box", "Prefect UI :4200<br><i>deployments · logs</i>", 120, 330, 210, 80, "fontSize=15;")
    server = d.box("box", "prefect-server<br><i>API + scheduler</i><br>cron 02:00 UTC", 420, 200, 200, 110, "fontSize=15;")
    flows = d.box("group_dashed_fill", "prefect-flows  (prefect serve)", 700, 60, 300, 360)
    d.box("text_left", "step-4-ingest<br>step-5-train<br>step-6-publish<br>step-7-serve<br>step-8-stream<br>"
          "scenario · stop-stream<br><b>retrain-pipeline</b> (4 → 5 → 6)", 725, 110, 260, 220)
    d.box("text_left", "tasks tagged component:&lt;id&gt;<br>→ the console lights them up", 725, 345, 270, 60,
          "fontSize=13;")
    targets = [
        d.box("dashed", "uv run dvc repro / push", 1070, 60, 230, 60, "fontSize=14;"),
        d.box("dashed", "uv run feast apply / materialize", 1070, 150, 230, 60, "fontSize=14;"),
        d.box("dashed", "uv run python -m fraud.training.*", 1070, 240, 230, 60, "fontSize=14;"),
        d.box("dashed", "docker compose up api · producer · consumer<br><i>(docker.sock)</i>", 1070, 330, 230, 80,
              "fontSize=14;"),
    ]
    prom = d.box("box", "Prometheus<br><i>DataDriftDetected</i>", 420, 500, 200, 80, "fontSize=15;")
    am = d.box("box", "Alertmanager :9093", 720, 510, 200, 60, "fontSize=15;")

    d.edge("arrow", user, console, extra="exitX=0.5;exitY=0;entryX=0;entryY=0.5;")
    d.edge("arrow", user, ui, extra="exitX=0.5;exitY=1;entryX=0;entryY=0.5;")
    d.edge("arrow", console, server, "create flow run", extra="exitX=1;exitY=0.5;entryX=0.6;entryY=0;")
    d.edge("dashed", server, console, "task states (poll)", extra="exitX=0;exitY=0.25;entryX=0.75;entryY=1;",
           label_pos=0.1)
    d.edge("arrow", ui, server, "Run", extra="exitX=1;exitY=0.5;entryX=0.3;entryY=1;")
    d.edge("arrow", server, flows, "dispatch")
    for t in targets:
        d.edge("arrow", flows, t, extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    d.edge("arrow", prom, am, "action=retrain")
    d.edge("orth", am, console, "webhook /alertmanager → retrain-pipeline",
           points=[(820, 625), (90, 625), (90, 130)], label_pos=-0.35, extra="exitX=0.5;exitY=1;entryX=0;entryY=0.5;" +
           ALERT)
    d.save("tutorial-10-automation.drawio")


if __name__ == "__main__":
    airport_analogy()
    architecture("tutorial-02-architecture.drawio", monitoring=False)
    docker_compose()
    feast()
    train()
    serve()
    kafka()
    architecture("tutorial-09-monitoring.drawio", monitoring=True)
    automation()
