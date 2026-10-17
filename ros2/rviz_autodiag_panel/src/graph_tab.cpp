// "Graph" tab: every publisher -> subscriber connection, colored by the QoS/type rules (GET /api/graph).
// Same data and layout as the dashboard's Graph tab, drawn natively so it sits next to the displays.
#include "rviz_autodiag_panel/autodiag_panel.hpp"

#include <algorithm>
#include <functional>
#include <utility>

#include <QComboBox>
#include <QDesktopServices>
#include <QFontMetrics>
#include <QGraphicsPathItem>
#include <QGraphicsScene>
#include <QGraphicsSceneHoverEvent>
#include <QGraphicsSceneMouseEvent>
#include <QGraphicsSimpleTextItem>
#include <QGraphicsView>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QLabel>
#include <QNetworkReply>
#include <QPainterPathStroker>
#include <QPushButton>
#include <QTabWidget>
#include <QTextBrowser>
#include <QUrl>
#include <QVBoxLayout>

namespace rviz_autodiag_panel
{

namespace
{
constexpr qreal kBoxW = 170;
constexpr qreal kBoxH = 32;
constexpr qreal kColGap = 110;
constexpr qreal kRowGap = 14;
constexpr qreal kPad = 14;
constexpr int kGraphTimeoutMs = 60000;  // inspects every visible topic

QColor statusColor(const QString & status)
{
  if (status == QLatin1String("error")) {return QColor(0xd2, 0x3f, 0x5a);}
  if (status == QLatin1String("warning")) {return QColor(0xe0, 0x93, 0x1f);}
  if (status == QLatin1String("waiting")) {return QColor(0x8f, 0x99, 0xa8);}
  return QColor(0x2a, 0xa7, 0x84);
}

int statusRank(const QString & status)
{
  return status == QLatin1String("error") ? 2 : (status == QLatin1String("warning") ? 1 : 0);
}

// `ros2 topic pub/echo` run as anonymous _ros2cli_<pid> nodes; name them by what they do, as the dashboard does.
QString idLabel(const QString & id, bool publisher)
{
  if (id.startsWith(QLatin1String("_ros2cli_"))) {
    return (publisher ? QStringLiteral("ros2 topic pub") : QStringLiteral("ros2 topic echo")) +
           QStringLiteral(" (") + id.mid(9) + ')';
  }
  if (id.startsWith(QLatin1String("transform_listener_impl_"))) {
    return QStringLiteral("TF listener");
  }
  return id;
}

QString nodeLabel(const QJsonObject & node)
{
  const QString id = node.value(QStringLiteral("id")).toString();
  return idLabel(id, !node.value(QStringLiteral("publishes")).toArray().isEmpty());
}

QString qosLine(const QJsonObject & qos)
{
  return QStringLiteral("%1 / %2").arg(qos.value(QStringLiteral("reliability")).toString(QStringLiteral("?")),
           qos.value(QStringLiteral("durability")).toString(QStringLiteral("?")));
}

/// A connection line: wide hit area, thicker on hover and when selected, dashed while nobody publishes.
class EdgeItem : public QGraphicsPathItem
{
public:
  EdgeItem(const QPainterPath & path, QString status, std::function<void(EdgeItem *)> on_click)
  : QGraphicsPathItem(path), status_(std::move(status)), on_click_(std::move(on_click))
  {
    setAcceptHoverEvents(true);
    setCursor(Qt::PointingHandCursor);
    setBrush(Qt::NoBrush);
    restyle();
  }

  void setChosen(bool chosen)
  {
    chosen_ = chosen;
    setZValue(chosen ? 1 : 0);
    restyle();
  }

  QPainterPath shape() const override
  {
    QPainterPathStroker stroker;
    stroker.setWidth(12);
    return stroker.createStroke(path());
  }

protected:
  void hoverEnterEvent(QGraphicsSceneHoverEvent *) override {hover_ = true; restyle();}
  void hoverLeaveEvent(QGraphicsSceneHoverEvent *) override {hover_ = false; restyle();}
  void mousePressEvent(QGraphicsSceneMouseEvent * event) override
  {
    if (event->button() == Qt::LeftButton && on_click_) {
      on_click_(this);
    }
    event->accept();
  }

private:
  void restyle()
  {
    const qreal width = status_ == QLatin1String("error") ? 3.0 : (status_ == QLatin1String("warning") ? 2.6 : 2.0);
    QPen pen(statusColor(status_), width + (hover_ ? 1.5 : 0.0) + (chosen_ ? 2.0 : 0.0));
    pen.setCapStyle(Qt::RoundCap);
    if (status_ == QLatin1String("waiting")) {
      pen.setStyle(Qt::DashLine);
    }
    setPen(pen);
  }

  QString status_;
  std::function<void(EdgeItem *)> on_click_;
  bool hover_{false};
  bool chosen_{false};
};

/// Scales the graph down to the dock width (never up), so it stays whole in RViz's narrow side panel.
class GraphView : public QGraphicsView
{
public:
  using QGraphicsView::QGraphicsView;

  void fit()
  {
    resetTransform();
    if (!scene() || scene()->sceneRect().width() <= 0) {
      return;
    }
    const qreal s = std::min<qreal>(1.0, (viewport()->width() - 4) / scene()->sceneRect().width());
    scale(s, s);
  }

protected:
  void resizeEvent(QResizeEvent * event) override
  {
    QGraphicsView::resizeEvent(event);
    fit();
  }
};

struct Layout
{
  QHash<QString, QPointF> pos;
  QSizeF size;
};

/// Columns by role (only publishes | both | only subscribes) with "nobody publishes" placeholders on the left,
/// ordered by two barycenter sweeps so lines cross less. The same layout as the dashboard's Graph tab.
Layout layoutGraph(const QJsonObject & data)
{
  QVector<QStringList> cols(3);
  for (const QJsonValue & value : data.value(QStringLiteral("nodes")).toArray()) {
    const QJsonObject n = value.toObject();
    const bool pubs = !n.value(QStringLiteral("publishes")).toArray().isEmpty();
    const bool subs = !n.value(QStringLiteral("subscribes")).toArray().isEmpty();
    cols[pubs && subs ? 1 : (pubs ? 0 : 2)].append(n.value(QStringLiteral("id")).toString());
  }
  QVector<QPair<QString, QString>> links;
  for (const QJsonValue & value : data.value(QStringLiteral("edges")).toArray()) {
    const QJsonObject e = value.toObject();
    links.append({e.value(QStringLiteral("source")).toString(), e.value(QStringLiteral("target")).toString()});
  }
  for (const QJsonValue & value : data.value(QStringLiteral("waiting")).toArray()) {
    const QJsonObject w = value.toObject();
    const QString ghost = QStringLiteral("ghost:") + w.value(QStringLiteral("topic")).toString();
    cols[0].append(ghost);
    for (const QJsonValue & sub : w.value(QStringLiteral("subscribers")).toArray()) {
      links.append({ghost, sub.toString()});
    }
  }
  QVector<QStringList *> used;
  for (QStringList & col : cols) {
    if (!col.isEmpty()) {
      used.append(&col);
    }
  }
  auto sweep = [&](QStringList & col, bool incoming) {
      QHash<QString, int> rank;
      for (const QStringList * c : used) {
        for (int i = 0; i < c->size(); ++i) {
          rank.insert(c->at(i), i);
        }
      }
      QHash<QString, double> score;
      for (const QString & id : col) {
        double sum = 0;
        int count = 0;
        for (const auto & link : links) {
          const QString & self = incoming ? link.second : link.first;
          const QString & other = incoming ? link.first : link.second;
          if (self == id && rank.contains(other)) {
            sum += rank.value(other);
            ++count;
          }
        }
        score.insert(id, count ? sum / count : rank.value(id));
      }
      std::sort(col.begin(), col.end(), [&score](const QString & a, const QString & b) {
          return score.value(a) != score.value(b) ? score.value(a) < score.value(b) : a < b;
        });
    };
  for (int pass = 0; pass < 2; ++pass) {
    for (int i = 1; i < used.size(); ++i) {
      sweep(*used[i], true);
    }
    for (int i = used.size() - 2; i >= 0; --i) {
      sweep(*used[i], false);
    }
  }
  Layout layout;
  int rows = 1;
  for (int i = 0; i < used.size(); ++i) {
    rows = std::max(rows, static_cast<int>(used[i]->size()));
    for (int j = 0; j < used[i]->size(); ++j) {
      layout.pos.insert(used[i]->at(j), QPointF(kPad + i * (kBoxW + kColGap), kPad + j * (kBoxH + kRowGap)));
    }
  }
  const int n = std::max(1, static_cast<int>(used.size()));
  layout.size = QSizeF(2 * kPad + n * kBoxW + (n - 1) * kColGap, 2 * kPad + rows * kBoxH + (rows - 1) * kRowGap);
  return layout;
}

QPainterPath curve(const QPointF & a, const QPointF & b)
{
  const QPointF p1(a.x() + kBoxW, a.y() + kBoxH / 2);
  const QPointF p2(b.x(), b.y() + kBoxH / 2);
  const qreal dx = std::max<qreal>(40, (p2.x() - p1.x()) / 2);
  QPainterPath path(p1);
  path.cubicTo(p1 + QPointF(dx, 0), p2 - QPointF(dx, 0), p2);
  return path;
}
}  // namespace

QWidget * AutoDiagPanel::buildGraphTab()
{
  graph_button_ = new QPushButton(tr("Check connections"));
  graph_button_->setToolTip(tr("Inspect every visible topic and draw who talks to whom (a few seconds)"));
  auto * legend = new QLabel(
    QStringLiteral("<small><span style='color:%1'>━━</span> %2 &nbsp; <span style='color:%3'>━━</span> %4 &nbsp; "
    "<span style='color:%5'>━━</span> %6 &nbsp; <span style='color:%7'>┅┅</span> %8</small>")
    .arg(statusColor(QStringLiteral("error")).name(), tr("no data gets through"),
    statusColor(QStringLiteral("warning")).name(), tr("warning"),
    statusColor(QStringLiteral("ok")).name(), tr("compatible"),
    statusColor(QStringLiteral("waiting")).name(), tr("nobody publishes")));
  legend->setWordWrap(true);
  graph_summary_ = new QLabel(
    tr("Every publisher → subscriber connection, checked with the same QoS and type rules as the Topic tab."));
  graph_summary_->setWordWrap(true);

  graph_scene_ = new QGraphicsScene(this);
  auto * view = new GraphView(graph_scene_);
  view->setRenderHint(QPainter::Antialiasing);
  view->setAlignment(Qt::AlignLeft | Qt::AlignTop);
  graph_view_ = view;

  graph_details_ = new QTextBrowser;
  graph_details_->setOpenLinks(false);
  graph_details_->setPlaceholderText(tr("Click a connection to see why it is broken and how to fix it."));
  connect(graph_details_, &QTextBrowser::anchorClicked, this, [this](const QUrl & url) {
      if (url.scheme() == QLatin1String("inspect")) {
        topic_combo_->setEditText(url.path());
        tabs_->setCurrentWidget(topic_view_->parentWidget());
        inspectTopic();
      } else {
        QDesktopServices::openUrl(url);
      }
    });
  connect(graph_button_, &QPushButton::clicked, this, &AutoDiagPanel::loadGraph);

  graph_button_->setObjectName(QStringLiteral("graphRefresh"));
  graph_summary_->setObjectName(QStringLiteral("graphSummary"));
  graph_view_->setObjectName(QStringLiteral("graphView"));
  graph_details_->setObjectName(QStringLiteral("graphDetails"));

  auto * tab = new QWidget;
  auto * layout = new QVBoxLayout(tab);
  auto * row = new QHBoxLayout;
  row->addWidget(graph_button_);
  row->addStretch();
  layout->addLayout(row);
  layout->addWidget(legend);
  layout->addWidget(graph_summary_);
  layout->addWidget(graph_view_, 3);
  layout->addWidget(graph_details_, 2);
  return tab;
}

void AutoDiagPanel::loadGraph()
{
  graph_loaded_ = true;
  graph_button_->setEnabled(false);
  graph_summary_->setText(tr("Inspecting every topic… this takes a few seconds."));
  QNetworkReply * reply = get(QStringLiteral("/api/graph"), kGraphTimeoutMs);
  connect(reply, &QNetworkReply::finished, this, [this, reply]() {
      reply->deleteLater();
      graph_button_->setEnabled(true);
      if (reply->error() != QNetworkReply::NoError) {
        graph_summary_->setText(errorText(reply));
        return;
      }
      const QJsonObject data = QJsonDocument::fromJson(reply->readAll()).object();
      if (data.value(QStringLiteral("state")).toString() != QLatin1String("ok")) {
        graph_scene_->clear();
        graph_details_->clear();
        graph_summary_->setText(data.value(QStringLiteral("error")).toString(tr("The ROS graph could not be read.")));
        return;
      }
      const QJsonObject c = data.value(QStringLiteral("counts")).toObject();
      graph_summary_->setText(
        tr("<b>%1 problem · %2 warning · %3 OK · %4 waiting</b><br><small>%5 of %6 topics inspected in %7 s%8. "
        "Compatible QoS does not prove that messages arrive.</small>")
        .arg(c.value(QStringLiteral("error")).toInt()).arg(c.value(QStringLiteral("warning")).toInt())
        .arg(c.value(QStringLiteral("ok")).toInt()).arg(c.value(QStringLiteral("waiting")).toInt())
        .arg(data.value(QStringLiteral("topics_inspected")).toInt())
        .arg(data.value(QStringLiteral("topics_total")).toInt())
        .arg(data.value(QStringLiteral("seconds")).toDouble(), 0, 'f', 1)
        .arg(data.value(QStringLiteral("truncated")).toBool() ? tr(" (limited; the rest are not shown)") : QString()));
      drawGraph(data);
    });
}

void AutoDiagPanel::drawGraph(const QJsonObject & data)
{
  graph_scene_->clear();
  graph_details_->clear();
  auto * view = static_cast<GraphView *>(graph_view_);
  const QJsonArray nodes = data.value(QStringLiteral("nodes")).toArray();
  const QJsonArray waiting = data.value(QStringLiteral("waiting")).toArray();
  if (nodes.isEmpty() && waiting.isEmpty()) {
    QGraphicsTextItem * text = graph_scene_->addText(
      tr("No publishers or subscribers found on the visible topics.\n"
      "Is ROS 2 sourced, and do your nodes use the same ROS_DOMAIN_ID?"));
    graph_scene_->setSceneRect(text->boundingRect());
    view->fit();
    return;
  }

  const Layout layout = layoutGraph(data);
  graph_scene_->setSceneRect(QRectF(QPointF(0, 0), layout.size));
  const QPalette palette = graph_view_->palette();
  // Text is a little larger than the panel's, so it stays readable when the graph is scaled to a narrow dock.
  QFont small_font = graph_view_->font();
  small_font.setPointSizeF(small_font.pointSizeF() * 1.05);
  QColor label_back = palette.color(QPalette::Base);
  label_back.setAlpha(215);

  auto choose = [this](EdgeItem * chosen) {
      for (QGraphicsItem * item : graph_scene_->items()) {
        if (auto * edge = dynamic_cast<EdgeItem *>(item)) {
          edge->setChosen(edge == chosen);
        }
      }
    };
  QVector<QRectF> placed;
  auto add_label = [&](const QString & text, const QPointF & center, const QColor & color) {
      auto * label = new QGraphicsSimpleTextItem(QFontMetrics(small_font).elidedText(text, Qt::ElideMiddle, 160));
      label->setFont(small_font);
      label->setBrush(color);
      const QRectF r = label->boundingRect();
      // Lines often meet near the middle: nudge a label up or down until it no longer covers another one.
      QRectF spot(center - QPointF(r.width() / 2 + 3, r.height() / 2 + 1), QSizeF(r.width() + 6, r.height() + 2));
      const qreal top = spot.top();
      auto overlaps = [&placed](const QRectF & rect) {
          return std::any_of(placed.begin(), placed.end(), [&rect](const QRectF & p) {return p.intersects(rect);});
        };
      for (int k = 1; k < 9 && overlaps(spot); ++k) {
        spot.moveTop(top + (k % 2 ? 1 : -1) * ((k + 1) / 2) * (spot.height() + 2));
      }
      placed.append(spot);
      QGraphicsRectItem * back = graph_scene_->addRect(QRectF(QPointF(0, 0), spot.size()), Qt::NoPen, label_back);
      back->setPos(spot.topLeft());
      back->setZValue(2);
      back->setAcceptedMouseButtons(Qt::NoButton);  // clicks go through to the line underneath
      label->setParentItem(back);
      label->setPos(3, 1);
    };

  // Worst connections are drawn last, on top.
  QVector<QJsonObject> edges;
  for (const QJsonValue & value : data.value(QStringLiteral("edges")).toArray()) {
    edges.append(value.toObject());
  }
  std::stable_sort(edges.begin(), edges.end(), [](const QJsonObject & a, const QJsonObject & b) {
      return statusRank(a.value(QStringLiteral("status")).toString()) <
      statusRank(b.value(QStringLiteral("status")).toString());
    });
  EdgeItem * worst = nullptr;
  QJsonObject worst_edge;
  for (const QJsonObject & e : edges) {
    const QString source = e.value(QStringLiteral("source")).toString();
    const QString target = e.value(QStringLiteral("target")).toString();
    if (!layout.pos.contains(source) || !layout.pos.contains(target)) {
      continue;
    }
    const QString status = e.value(QStringLiteral("status")).toString();
    const QPointF a = layout.pos.value(source);
    const QPointF b = layout.pos.value(target);
    auto * item = new EdgeItem(curve(a, b), status, [this, e, choose](EdgeItem * self) {
          choose(self);
          showEdgeDetails(e);
        });
    QStringList topics;
    for (const QJsonValue & t : e.value(QStringLiteral("topics")).toArray()) {
      topics << t.toObject().value(QStringLiteral("topic")).toString();
    }
    item->setToolTip(QStringLiteral("%1 → %2\n%3").arg(idLabel(source, true), idLabel(target, false),
      topics.join(QStringLiteral(", "))));
    graph_scene_->addItem(item);
    add_label(topics.size() == 1 ? topics.first() : tr("%n topics", "", topics.size()),
      QPointF((a.x() + kBoxW + b.x()) / 2, (a.y() + b.y()) / 2 + kBoxH / 2), statusColor(status));
    if (status != QLatin1String("ok")) {
      worst = item;  // edges are sorted, so the last non-OK one is the worst
      worst_edge = e;
    }
  }
  EdgeItem * first_waiting = nullptr;
  QJsonObject first_waiting_topic;
  for (const QJsonValue & value : waiting) {
    const QJsonObject w = value.toObject();
    const QString ghost = QStringLiteral("ghost:") + w.value(QStringLiteral("topic")).toString();
    for (const QJsonValue & sub : w.value(QStringLiteral("subscribers")).toArray()) {
      if (!layout.pos.contains(ghost) || !layout.pos.contains(sub.toString())) {
        continue;
      }
      auto * item = new EdgeItem(curve(layout.pos.value(ghost), layout.pos.value(sub.toString())),
          QStringLiteral("waiting"), [this, w, choose](EdgeItem * self) {
            choose(self);
            showWaitingDetails(w);
          });
      item->setToolTip(tr("%1 waits for %2").arg(idLabel(sub.toString(), false),
        w.value(QStringLiteral("topic")).toString()));
      graph_scene_->addItem(item);
      if (!first_waiting) {
        first_waiting = item;
        first_waiting_topic = w;
      }
    }
  }

  QHash<QString, QJsonObject> by_id;
  for (const QJsonValue & value : nodes) {
    by_id.insert(value.toObject().value(QStringLiteral("id")).toString(), value.toObject());
  }
  for (auto it = layout.pos.constBegin(); it != layout.pos.constEnd(); ++it) {
    const bool ghost = it.key().startsWith(QLatin1String("ghost:"));
    // A placeholder shows just the topic in a dashed box; the legend and tooltip say nobody publishes it.
    const QString text = ghost ? it.key().mid(6) : nodeLabel(by_id.value(it.key()));
    QPainterPath box;
    box.addRoundedRect(QRectF(it.value(), QSizeF(kBoxW, kBoxH)), 7, 7);
    QPen border(palette.color(QPalette::Mid), 1.2);
    if (ghost) {
      border.setStyle(Qt::DashLine);
    }
    QGraphicsPathItem * node = graph_scene_->addPath(box, border,
        ghost ? QBrush(Qt::NoBrush) : palette.brush(QPalette::Button));
    node->setZValue(3);
    node->setToolTip(ghost ? tr("nobody publishes %1").arg(text) : text);
    QFont font = graph_view_->font();
    font.setPointSizeF(font.pointSizeF() * 1.15);
    font.setItalic(ghost);
    font.setBold(!ghost);
    auto * label = new QGraphicsSimpleTextItem(
      QFontMetrics(font).elidedText(text, Qt::ElideMiddle, static_cast<int>(kBoxW - 12)), node);
    label->setFont(font);
    label->setBrush(ghost ? palette.color(QPalette::Mid) : palette.color(QPalette::ButtonText));
    const QRectF r = label->boundingRect();
    label->setPos(it.value() + QPointF((kBoxW - r.width()) / 2, (kBoxH - r.height()) / 2));
  }
  view->fit();

  // Open the worst connection right away, as the dashboard does.
  if (worst) {
    choose(worst);
    showEdgeDetails(worst_edge);
  } else if (first_waiting) {
    choose(first_waiting);
    showWaitingDetails(first_waiting_topic);
  }
}

void AutoDiagPanel::showEdgeDetails(const QJsonObject & edge)
{
  QString html = QStringLiteral("<p><b>%1</b> → <b>%2</b></p>").arg(
    idLabel(edge.value(QStringLiteral("source")).toString(), true).toHtmlEscaped(),
    idLabel(edge.value(QStringLiteral("target")).toString(), false).toHtmlEscaped());
  for (const QJsonValue & value : edge.value(QStringLiteral("topics")).toArray()) {
    const QJsonObject t = value.toObject();
    const QString topic = t.value(QStringLiteral("topic")).toString().toHtmlEscaped();
    html += QStringLiteral("<p><code>%1</code> <small>%2</small> · <a href='inspect:%1'>%3</a><br>"
        "<small>%4</small></p>").arg(topic, t.value(QStringLiteral("type")).toString().toHtmlEscaped(),
      tr("Inspect topic"),
      tr("Publisher offers %1 · subscriber requests %2").arg(
        qosLine(t.value(QStringLiteral("publisher_qos")).toObject()),
        qosLine(t.value(QStringLiteral("subscriber_qos")).toObject())).toHtmlEscaped());
    const QJsonArray findings = t.value(QStringLiteral("findings")).toArray();
    if (findings.isEmpty()) {
      html += tr("<p style='color:#0f8a64'>QoS and message types are compatible. That does not prove that messages "
          "arrive.</p>");
    }
    for (const QJsonValue & f_value : findings) {
      const QJsonObject f = f_value.toObject();
      const QString severity = f.value(QStringLiteral("severity")).toString();
      html += QStringLiteral("<p style='color:%1'><b>%2 %3</b> %4</p><p><b>%5</b> %6</p>").arg(
        severity == QLatin1String("error") ? QStringLiteral("#c2304a") : QStringLiteral("#a86400"),
        severityMark(severity), f.value(QStringLiteral("code")).toString().toHtmlEscaped(),
        f.value(QStringLiteral("summary")).toString().toHtmlEscaped(), tr("Next step:"),
        f.value(QStringLiteral("recommended_action")).toString().toHtmlEscaped());
      QStringList docs;
      for (const QJsonValue & d_value : f.value(QStringLiteral("documentation")).toArray()) {
        const QJsonObject d = d_value.toObject();
        docs << QStringLiteral("<a href='%1'>%2 ↗</a>").arg(d.value(QStringLiteral("url")).toString().toHtmlEscaped(),
          d.value(QStringLiteral("label")).toString().toHtmlEscaped());
      }
      if (!docs.isEmpty()) {
        html += QStringLiteral("<p>") + docs.join(QStringLiteral(" · ")) + QStringLiteral("</p>");
      }
    }
  }
  graph_details_->setHtml(html);
}

void AutoDiagPanel::showWaitingDetails(const QJsonObject & waiting)
{
  QStringList subscribers;
  for (const QJsonValue & value : waiting.value(QStringLiteral("subscribers")).toArray()) {
    subscribers << idLabel(value.toString(), false);
  }
  const QString topic = waiting.value(QStringLiteral("topic")).toString().toHtmlEscaped();
  const QString type = waiting.value(QStringLiteral("type")).toString();
  graph_details_->setHtml(
    tr("<p style='color:#a86400'><b>▲ Waiting</b> <code>%1</code></p><p>%2 subscribe%3 to <code>%1</code>%4, but no "
    "publisher is visible from this machine.</p><p><b>Next step:</b> Start the node that publishes it, check the "
    "topic name and remapping, or compare hosts if it runs on another machine or container (domain ID, discovery "
    "range, RMW).</p><p><a href='inspect:%1'>Inspect topic</a></p>")
    .arg(topic, subscribers.join(QStringLiteral(", ")).toHtmlEscaped(),
    subscribers.size() == 1 ? QStringLiteral("s") : QString(),
    type.isEmpty() ? QString() : QStringLiteral(" (%1)").arg(type.toHtmlEscaped())));
}

}  // namespace rviz_autodiag_panel
