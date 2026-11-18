"""Generate the ArchiMate 3 views of the lab as draw.io files, in a brand theme.

    uv run --no-project python docs/diagrams/generate_archimate.py [--brand aurora|majlisofai] [--out DIR]
    make diagrams BRAND=aurora                                       # + exports PNG

The .drawio files are the editable source: open them in draw.io / diagrams.net
(ArchiMate 3 shape library) to tweak the layout by hand.
"""

from pathlib import Path
from xml.sax.saxutils import quoteattr

import brand

T, OUT = brand.cli(Path(__file__).parent)
A = T.archimate
FONT = brand.font(T)
BASE = f"html=1;outlineConnect=0;whiteSpace=wrap;fontSize=12;{FONT}fontColor={T.text};strokeWidth={T.node.width};"
BUSINESS = f"fillColor={A.business.fill};strokeColor={A.business.stroke};"
APPLICATION = f"fillColor={A.application.fill};strokeColor={A.application.stroke};"
TECHNOLOGY = f"fillColor={A.technology.fill};strokeColor={A.technology.stroke};"
FOCAL = f"strokeColor={T.focal.stroke};strokeWidth={T.focal.width};"

ELEMENTS = {
    # business layer
    "actor": f"{BASE}{BUSINESS}shape=mxgraph.archimate3.application;appType=actor;archiType=square;",
    "b_process": f"{BASE}{BUSINESS}shape=mxgraph.archimate3.application;appType=proc;archiType=rounded;",
    "b_service": f"{BASE}{BUSINESS}shape=mxgraph.archimate3.application;appType=serv;archiType=rounded;",
    "b_event": f"{BASE}{BUSINESS}shape=mxgraph.archimate3.application;appType=event;archiType=rounded;",
    "b_object": f"{BASE}{BUSINESS}shape=mxgraph.archimate3.businessObject;overflow=fill;",
    # application layer
    "component": f"{BASE}{APPLICATION}shape=mxgraph.archimate3.application;appType=comp;archiType=square;",
    "a_service": f"{BASE}{APPLICATION}shape=mxgraph.archimate3.application;appType=serv;archiType=rounded;",
    "a_process": f"{BASE}{APPLICATION}shape=mxgraph.archimate3.application;appType=proc;archiType=rounded;",
    "a_function": f"{BASE}{APPLICATION}shape=mxgraph.archimate3.application;appType=func;archiType=rounded;",
    "a_event": f"{BASE}{APPLICATION}shape=mxgraph.archimate3.application;appType=event;archiType=rounded;",
    "data": f"{BASE}{APPLICATION}shape=mxgraph.archimate3.businessObject;overflow=fill;",
    # technology layer
    "node": f"{BASE}{TECHNOLOGY}shape=mxgraph.archimate3.application;appType=node;archiType=square;"
            "verticalAlign=top;align=left;spacingLeft=10;spacingTop=4;fontStyle=1;",
    "device": f"{BASE}{TECHNOLOGY}shape=mxgraph.archimate3.application;appType=device;archiType=square;",
    "sys_sw": f"{BASE}{TECHNOLOGY}shape=mxgraph.archimate3.application;appType=sysSw;archiType=square;",
    "t_service": f"{BASE}{TECHNOLOGY}shape=mxgraph.archimate3.application;appType=serv;archiType=rounded;",
    "artifact": f"{BASE}{TECHNOLOGY}shape=mxgraph.archimate3.artifact;",
    # grouping / layer bands / notes
    "grouping": f"html=1;whiteSpace=wrap;fillColor=none;dashed=1;dashPattern=8 4;strokeColor={A.grouping};{FONT}"
                f"fontColor={T.text};verticalAlign=top;align=left;spacingLeft=8;spacingTop=2;fontStyle=1;fontSize=13;",
    "band": f"html=1;whiteSpace=wrap;strokeColor={T.band_stroke};verticalAlign=top;align=left;spacingLeft=10;"
            f"spacingTop=4;fontStyle=1;fontSize=15;{FONT}fontColor={T.muted};",
    "title": f"text;html=1;align=left;verticalAlign=middle;fontSize=22;fontStyle=1;{FONT}fontColor={T.text};",
    "note": f"text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;fontSize=11;{FONT}fontColor={T.muted};",
}

EDGE = (f"html=1;rounded=0;edgeStyle=orthogonalEdgeStyle;fontSize=10;{FONT}fontColor={T.muted};"
        f"labelBackgroundColor={T.edge_label_bg};strokeColor={T.edge};")
RELATIONS = {
    "serving": f"{EDGE}endArrow=open;endFill=0;",
    "triggering": f"{EDGE}endArrow=block;endFill=1;",
    "flow": f"{EDGE}endArrow=block;endFill=1;dashed=1;dashPattern=6 4;",
    "access": f"{EDGE}endArrow=open;endFill=0;endSize=4;dashed=1;dashPattern=1 3;",
    "realization": f"{EDGE}endArrow=block;endFill=0;dashed=1;",
    "assignment": f"{EDGE}endArrow=block;endFill=1;startArrow=oval;startFill=1;",
    "composition": f"{EDGE}startArrow=diamondThin;startFill=1;startSize=12;endArrow=none;",
}


class Diagram:
    def __init__(self, name: str, width: int, height: int) -> None:
        self.name, self.width, self.height = name, width, height
        self.cells: list[str] = []
        self.n = 0

    def _id(self) -> str:
        self.n += 1
        return f"c{self.n}"

    def box(self, kind: str, label: str, x: int, y: int, w: int = 160, h: int = 60, fill: str | None = None,
            extra: str = "") -> str:
        cid = self._id()
        style = ELEMENTS[kind] + (f"fillColor={fill};" if fill else "") + extra
        self.cells.append(
            f'<mxCell id="{cid}" value={quoteattr(label)} style={quoteattr(style)} vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return cid

    def rel(self, kind: str, src: str, tgt: str, label: str = "", style: str = "", points=(),
            label_pos: float = 0) -> str:
        cid = self._id()
        pts = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in points)
        self.cells.append(
            f'<mxCell id="{cid}" value={quoteattr(label)} style={quoteattr(RELATIONS[kind] + style)} edge="1" '
            f'parent="1" source="{src}" target="{tgt}"><mxGeometry x="{label_pos}" relative="1" as="geometry">'
            + (f'<Array as="points">{pts}</Array>' if pts else "") + "</mxGeometry></mxCell>")
        return cid

    def legend(self, x: int, y: int) -> None:
        self.box("grouping", "Legend — ArchiMate 3 relationships", x, y, 300, 250)
        for i, kind in enumerate(RELATIONS):
            yy = y + 38 + i * 30
            a = self.box("note", "", x + 15, yy, 1, 1)
            b = self.box("note", "", x + 115, yy, 1, 1)
            self.rel(kind, a, b)
            self.box("note", kind, x + 130, yy - 8, 150, 20)

    def save(self, filename: str) -> None:
        xml = (
            '<mxfile host="drawio" type="device">'
            f'<diagram name={quoteattr(self.name)} id="{filename}">'
            f'<mxGraphModel grid="1" gridSize="10" guides="1" page="1" pageWidth="{self.width}" '
            f'pageHeight="{self.height}" background="{T.canvas}" math="0" shadow="0"><root>'
            '<mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(self.cells) +
            "</root></mxGraphModel></diagram></mxfile>\n")
        (OUT / filename).write_text(xml)
        print(f"wrote {OUT / filename}")


def architecture() -> None:
    """Layered view: business, application and technology layers."""
    d = Diagram("Airport fraud detection - layered view", 1800, 1660)
    d.box("title", "Airport Real-Time Fraud Detection — ArchiMate layered view", 40, 10, 1200, 40)

    # layer bands (drawn first = behind)
    d.box("band", "Business layer", 30, 60, 1740, 250, fill=A.bands[0])
    d.box("band", "Application layer", 30, 330, 1740, 520, fill=A.bands[1])
    d.box("band", "", 30, 870, 1740, 500, fill=A.bands[2])
    d.box("band", "Technology layer — one laptop, Docker Compose (no Kubernetes)", 30, 1340, 900, 30, fill="none")

    # ── business ──
    passenger = d.box("actor", "Passenger<br>(card holder)", 60, 110, 140, 60)
    merchant = d.box("actor", "Airport merchant", 60, 210, 140, 60)
    pay_event = d.box("b_event", "Card payment<br>initiated", 260, 160, 140, 60)
    pay = d.box("b_process", "Pay at airport<br>merchant", 450, 160, 150, 60)
    screen = d.box("b_process", "Screen payment<br>for fraud", 820, 160, 160, 60)
    investigate = d.box("b_process", "Investigate<br>fraud alert", 1100, 160, 150, 60)
    analyst = d.box("actor", "Fraud analyst", 1100, 70, 150, 55)
    b_service = d.box("b_service", "Real-time fraud<br>screening", 820, 70, 160, 55)
    alert_obj = d.box("b_object", "Fraud alert", 1300, 165, 120, 55)
    ml_engineer = d.box("actor", "ML engineer", 1560, 70, 160, 55)
    lifecycle = d.box("b_process", "Manage fraud<br>model lifecycle", 1560, 160, 160, 60)

    d.rel("assignment", passenger, pay_event)
    d.rel("assignment", merchant, pay_event)
    d.rel("triggering", pay_event, pay)
    d.rel("triggering", pay, screen)
    d.rel("triggering", screen, investigate)
    d.rel("assignment", analyst, investigate)
    d.rel("realization", screen, b_service)
    d.rel("access", investigate, alert_obj)
    d.rel("assignment", ml_engineer, lifecycle)

    # ── application: four groupings = the four building blocks of the lab ──
    d.box("grouping", "Data & features", 50, 370, 360, 460)
    d.box("grouping", "ML platform", 430, 370, 360, 460)
    d.box("grouping", "Real-time detection", 810, 370, 560, 460)
    d.box("grouping", "Model monitoring", 1390, 370, 360, 460)

    dvc = d.box("component", "DVC data pipeline<br><i>generate → features</i>", 70, 410, 170, 65)
    feast = d.box("component", "Feast feature store", 70, 560, 170, 65)
    online_svc = d.box("a_service", "Online / historical<br>feature service", 250, 470, 150, 60)
    profile = d.box("data", "Passenger profile<br>features", 250, 680, 140, 60)

    trainer = d.box("component", "Model trainer<br><i>point-in-time join · sklearn</i>", 450, 410, 160, 65)
    mlflow = d.box("component", "MLflow tracking<br>&amp; model registry", 450, 560, 160, 65)
    registry_svc = d.box("a_service", "Model registry<br>service", 630, 470, 145, 60)
    model = d.box("data", "Fraud model<br>@champion", 630, 680, 140, 60)

    simulator = d.box("component", "Payment simulator<br><i>Kafka producer</i>", 830, 410, 160, 65)
    consumer = d.box("component", "Fraud consumer<br><i>consumer group ×N</i>", 1010, 410, 160, 65)
    scoring_svc = d.box("a_service", "Fraud scoring<br>service /predict", 1015, 525, 150, 55)
    api = d.box("component", "Fraud scoring API<br><i>FastAPI</i>", 1010, 640, 160, 65, extra=FOCAL)  # focal
    payment = d.box("data", "Payment event<br><i>airport.transactions</i>", 830, 560, 135, 60)
    decision = d.box("data", "Fraud decision<br>&amp; alert", 1210, 560, 140, 60)

    evidently = d.box("component", "Evidently<br>drift monitor", 1410, 410, 160, 65)
    drift_svc = d.box("a_service", "Drift detection<br>service", 1590, 525, 145, 55)
    report = d.box("data", "Drift report", 1410, 680, 130, 55)

    d.rel("flow", dvc, feast, "parquet")
    d.rel("realization", feast, online_svc)
    d.rel("access", feast, profile)
    d.rel("serving", online_svc, trainer)
    d.rel("flow", trainer, mlflow, "runs, models")
    d.rel("realization", mlflow, registry_svc)
    d.rel("access", mlflow, model)
    d.rel("flow", simulator, consumer)
    d.rel("access", simulator, payment, "", "exitX=0.4;exitY=1;entryX=0.5;entryY=0;")
    d.rel("realization", api, scoring_svc)
    d.rel("serving", scoring_svc, consumer)
    d.rel("access", consumer, decision, "", "exitX=1;exitY=0.75;entryX=0.5;entryY=0;")
    d.rel("composition", consumer, evidently)
    d.rel("realization", evidently, drift_svc, "", "exitX=1;exitY=0.5;entryX=0.3;entryY=0;")
    d.rel("access", evidently, report)

    # cross-layer: application services serve the business processes (routed through the band gap)
    d.rel("serving", scoring_svc, screen, "", "exitX=1;exitY=0.5;entryX=0.5;entryY=1;",
          points=[(1190, 552), (1190, 320), (900, 320)])
    d.rel("serving", registry_svc, lifecycle, "", "exitX=0.5;exitY=0;entryX=0.25;entryY=1;",
          points=[(702, 290), (1600, 290)])
    d.rel("serving", drift_svc, lifecycle, "", "exitX=0.62;exitY=0;entryX=0.75;entryY=1;")

    # the API's dependencies run under the groupings, through the gaps between them
    d.rel("serving", online_svc, api, "online lookup (Redis)", "exitX=1;exitY=0.75;entryX=0.3;entryY=1;",
          points=[(420, 515), (420, 800), (1058, 800)], label_pos=0.1)
    d.rel("serving", registry_svc, api, "load @champion", "exitX=1;exitY=0.75;entryX=0.7;entryY=1;",
          points=[(800, 515), (800, 775), (1122, 775)], label_pos=0.2)

    # ── technology ──
    streaming = d.box("t_service", "Event streaming", 830, 900, 150, 50)
    kv = d.box("t_service", "Key-value store", 70, 900, 150, 50)
    metrics = d.box("t_service", "Metrics, dashboards &amp; alerting", 1440, 900, 200, 50)
    d.box("device", "Laptop", 1660, 900, 90, 50)
    d.box("node", "Docker Desktop · docker compose", 50, 975, 1700, 270)
    redis = d.box("sys_sw", "Redis<br><i>Feast online store</i>", 70, 1030, 160, 65)
    d.box("sys_sw", "Python 3.11 + uv<br><i>fraud-lab-app image</i>", 250, 1030, 160, 65)
    mlflow_srv = d.box("sys_sw", "MLflow server", 450, 1030, 150, 65)
    postgres = d.box("sys_sw", "PostgreSQL<br><i>runs &amp; registry</i>", 620, 1030, 150, 65)
    kafka = d.box("sys_sw", "Apache Kafka 3.9<br><i>KRaft, 3 partitions</i>", 830, 1030, 170, 65)
    d.box("sys_sw", "Kafka UI", 1020, 1030, 120, 65)
    prometheus = d.box("sys_sw", "Prometheus<br><i>+ alert rules</i>", 1180, 1030, 150, 65)
    grafana = d.box("sys_sw", "Grafana", 1350, 1030, 130, 65)
    exporters = d.box("sys_sw", "kafka-exporter · redis-exporter<br>cAdvisor", 1500, 1030, 230, 65)
    alertmanager = d.box("sys_sw", "Alertmanager", 1180, 1150, 150, 60)
    prefect = d.box("sys_sw", "Prefect<br><i>server + flows</i>", 1530, 1150, 150, 60)

    d.box("artifact", "transactions.parquet<br>passenger_features.parquet", 50, 1275, 200, 70)
    d.box("artifact", "dvc-storage/<br><i>DVC remote</i>", 270, 1275, 140, 70)
    d.box("artifact", "MLmodel + model.pkl<br>reference.parquet", 450, 1275, 180, 70)
    d.box("artifact", "docker-compose.yml<br>.env (secrets)", 830, 1275, 170, 70)

    d.rel("realization", kafka, streaming)
    d.rel("realization", redis, kv)
    d.rel("realization", prometheus, metrics, "", "exitX=0.5;exitY=0;entryX=0.2;entryY=1;")
    d.rel("realization", grafana, metrics, "", "exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
    d.rel("serving", exporters, prometheus, "", "exitX=0.5;exitY=1;entryX=1;entryY=0.75;",
          points=[(1615, 1120), (1345, 1120), (1345, 1079)])
    d.rel("serving", postgres, mlflow_srv)
    d.rel("serving", prometheus, alertmanager, "", "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    d.rel("serving", alertmanager, prefect, "drift → retrain")

    # technology serves application: short vertical edges through free columns
    d.rel("serving", streaming, simulator, "", "exitX=0.95;exitY=0;entryX=0.9;entryY=1;")
    d.rel("serving", kv, feast, "", "exitX=0.5;exitY=0;entryX=0.45;entryY=1;")
    d.rel("realization", mlflow_srv, mlflow, "", "exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
    d.rel("serving", metrics, evidently, "", "exitX=0.55;exitY=0;entryX=0.92;entryY=1;")

    d.legend(30, 1390)
    d.save("01-architecture-archimate.drawio")


def workflow() -> None:
    """Process view: lab steps 4-8 + monitoring, with the retraining loop."""
    d = Diagram("Airport fraud detection - workflow view", 1760, 1660)
    d.box("title", "Workflow — from data ingestion to model serving and monitoring (ArchiMate process view)",
          40, 10, 1500, 40)

    rows = [
        ("4 · Ingest — DVC + Feast  (make ingest)", ("a_event", "New data /<br>params changed"), [
            "Generate airport<br>payments", "Build passenger<br>features", "Push data version<br><i>dvc push</i>",
            "Register features<br><i>feast apply</i>", "Materialize to<br>Redis"],
         [(0, "transactions.parquet"), (1, "passenger_features<br>.parquet"), (4, "Online features<br>(Redis)")],
         ["DVC pipeline", "Feast feature store"]),
        ("5 · Train — MLflow tracking  (make train)", None, [
            "Point-in-time join<br><i>Feast historical</i>", "Time-based split<br>train · valid · test",
            "Fit 3 candidates<br><i>LR · RF · HGB</i>", "Tune decision<br>threshold (valid)", "Log run to MLflow"],
         [(0, "Training dataset"), (4, "MLflow run<br>metrics · model · reference")],
         ["Model trainer", "MLflow tracking"]),
        ("6 · Publish — MLflow registry  (make publish)", None, [
            "Select best run<br><i>test PR-AUC</i>", "Apply quality gate<br><i>≥ min, &gt; champion</i>",
            "Register model<br>version", "Set alias @champion<br>(old → @previous)", "Hot-reload API<br><i>POST /reload</i>"],
         [(3, "airport-fraud-detector<br>@champion")],
         ["MLflow model registry"]),
        ("7 · Serve — FastAPI  (make serve · make predict)", ("a_event", "Scoring<br>request"), [
            "Validate<br>transaction", "Fetch passenger<br>features (Feast)", "Build model frame<br><i>shared contract</i>",
            "Predict fraud<br>probability", "Apply threshold<br>&amp; respond"],
         [(1, "Online features<br>(Redis)"), (4, "Fraud decision")],
         ["Fraud scoring API"]),
        ("8 · Real-time with Kafka  (make stream · make scale)", ("a_event", "Card payment<br>at airport"), [
            "Publish payment<br><i>key = passenger_id</i>", "Consume partition<br><i>group fraud-detector</i>",
            "Score via<br>/predict", "Publish decision", "Raise fraud alert"],
         [(0, "airport.transactions"), (3, "airport.predictions"), (4, "airport.fraud-alerts")],
         ["Payment simulator", "Fraud consumer ×N", "Apache Kafka"]),
        ("Monitor — Prometheus · Grafana · Evidently", None, [
            "Scrape metrics<br><i>app + infra</i>", "Evaluate data drift<br><i>Evidently / 200 txns</i>",
            "Evaluate alert rules", "Visualize in Grafana"],
         [(1, "drift_report.html"), (2, "Prometheus metrics")],
         ["Prometheus", "Grafana", "Evidently"]),
    ]

    row_h, gap, x0, y0 = 190, 25, 60, 70
    box_w, box_h, step = 165, 60, 195
    groups, ends = [], {}
    for i, (title, event, steps, data, components) in enumerate(rows):
        y = y0 + i * (row_h + gap)
        groups.append(d.box("grouping", title, x0, y, 1340, row_h))
        x = x0 + 20
        prev = None
        if event:
            prev = d.box(event[0], event[1], x, y + 40, 120, box_h)
            x += 150
        procs = []
        for label in steps:
            p = d.box("a_process", label, x, y + 40, box_w, box_h)
            if prev:
                d.rel("triggering", prev, p)
            procs.append(p)
            prev, x = p, x + step
        ends[i] = (procs[0], procs[-1])
        for idx, label in data:
            obj = d.box("data", label, x0 + 20 + (150 if event else 0) + idx * step, y + 125, box_w, 50)
            d.rel("access", procs[idx], obj)
        # components assigned to the step: one column, one straight edge each
        comp_h, comp_gap = 46, 12
        top = y + (row_h - len(components) * comp_h - (len(components) - 1) * comp_gap) / 2
        for j, name in enumerate(components):
            cy = top + j * (comp_h + comp_gap)
            c = d.box("component", name, 1460, int(cy), 220, comp_h)
            d.rel("assignment", c, groups[-1], "",
                  f"exitX=0;exitY=0.5;entryX=1;entryY={(cy + comp_h / 2 - y) / row_h:.3f};")

    # steps trigger each other (left margin, top to bottom)
    for a, b in zip(groups, groups[1:]):
        d.rel("triggering", a, b, "", "exitX=0.01;exitY=1;entryX=0.01;entryY=0;")

    # monitoring closes the loop: drift / fraud-rate alert -> retrain
    loop = d.box("a_event", "Drift or fraud-rate<br>alert fires", x0 + 20 + 4 * step, y0 + 5 * (row_h + gap) + 40, 150, box_h)
    d.rel("triggering", ends[5][1], loop)
    loop_y = y0 + 5 * (row_h + gap) + 40 + box_h // 2
    d.rel("triggering", loop, groups[0], "retrain loop",
          f"exitX=1;exitY=0.5;entryX=1;entryY=0.12;strokeWidth={T.focal.width};strokeColor={T.alert};fontColor={T.alert};",
          points=[(1425, loop_y), (1425, y0 + 23)], label_pos=0.1)

    d.legend(1440, 1370)
    d.save("02-workflow-archimate.drawio")


if __name__ == "__main__":
    architecture()
    workflow()
