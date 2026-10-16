#include "rviz_autodiag_panel/autodiag_panel.hpp"

#include <functional>

#include <QCheckBox>
#include <QComboBox>
#include <QDesktopServices>
#include <QFormLayout>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QPushButton>
#include <QRegularExpression>
#include <QSignalBlocker>
#include <QTabWidget>
#include <QTextBrowser>
#include <QTextCursor>
#include <QTextDocument>
#include <QTimer>
#include <QUrl>
#include <QUrlQuery>
#include <QVBoxLayout>

#include <pluginlib/class_list_macros.hpp>
#include <rviz_common/config.hpp>
#include <rviz_common/display.hpp>
#include <rviz_common/display_context.hpp>
#include <rviz_common/display_group.hpp>
#include <rviz_common/properties/status_property.hpp>

namespace rviz_autodiag_panel
{

namespace
{
constexpr int kStreamTimeoutMs = 300000;  // local models on CPU can take a while
constexpr int kAutoRefreshMs = 30000;
constexpr int kConnectRetries = 15;       // with kConnectRetryMs: wait up to 30 s for the server
constexpr int kConnectRetryMs = 2000;

QJsonObject parseObject(const QByteArray & data)
{
  return QJsonDocument::fromJson(data).object();
}
}  // namespace

AutoDiagPanel::AutoDiagPanel(QWidget * parent)
: rviz_common::Panel(parent), net_(new QNetworkAccessManager(this))
{
  // --- connection row
  server_edit_ = new QLineEdit(qEnvironmentVariable("AUTODIAG_SERVER_URL", QStringLiteral("http://127.0.0.1:8080")));
  server_edit_->setToolTip(tr("URL of the AutoDiag server (start it with: dds-autodiag serve)"));
  token_edit_ = new QLineEdit(qEnvironmentVariable("AUTODIAG_UI_TOKEN"));
  token_edit_->setEchoMode(QLineEdit::Password);
  token_edit_->setPlaceholderText(tr("token (only if AUTODIAG_UI_TOKEN is set)"));
  auto * connect_button = new QPushButton(tr("Connect"));
  auto * dashboard_button = new QPushButton(tr("Dashboard"));
  dashboard_button->setToolTip(tr("Open the full AutoDiag dashboard in a browser"));
  connection_label_ = new QLabel(tr("Not connected"));
  connection_label_->setWordWrap(true);

  auto * server_row = new QHBoxLayout;
  server_row->addWidget(server_edit_, 3);
  server_row->addWidget(connect_button);
  server_row->addWidget(dashboard_button);

  // --- health tab
  health_label_ = new QLabel(tr("Press Refresh to check this machine."));
  health_label_->setWordWrap(true);
  findings_list_ = new QListWidget;
  findings_list_->setWordWrap(true);
  findings_list_->setAlternatingRowColors(true);
  auto * refresh_button = new QPushButton(tr("Refresh"));
  auto_refresh_check_ = new QCheckBox(tr("every 30 s"));
  auto_refresh_timer_ = new QTimer(this);
  auto_refresh_timer_->setInterval(kAutoRefreshMs);

  auto * health_tab = new QWidget;
  auto * health_layout = new QVBoxLayout(health_tab);
  auto * health_row = new QHBoxLayout;
  health_row->addWidget(refresh_button);
  health_row->addWidget(auto_refresh_check_);
  health_row->addStretch();
  health_layout->addLayout(health_row);
  health_layout->addWidget(health_label_);
  health_layout->addWidget(findings_list_, 1);

  // --- topic tab
  topic_combo_ = new QComboBox;
  topic_combo_->setEditable(true);
  topic_combo_->setInsertPolicy(QComboBox::NoInsert);
  topic_combo_->setToolTip(tr("Topics used by RViz displays are listed first (⚠ = display reports a problem)"));
  auto * topics_button = new QPushButton(tr("↻"));
  topics_button->setToolTip(tr("Reload topics"));
  topics_button->setMaximumWidth(36);
  auto * inspect_button = new QPushButton(tr("Inspect"));
  topic_view_ = new QTextBrowser;
  topic_view_->setOpenExternalLinks(true);
  topic_view_->setPlaceholderText(tr("Pick a topic and press Inspect to see its publishers, subscribers and QoS."));

  auto * topic_tab = new QWidget;
  auto * topic_layout = new QVBoxLayout(topic_tab);
  auto * topic_row = new QHBoxLayout;
  topic_row->addWidget(topic_combo_, 1);
  topic_row->addWidget(topics_button);
  topic_row->addWidget(inspect_button);
  topic_layout->addLayout(topic_row);
  topic_layout->addWidget(topic_view_, 1);

  // --- AI tab
  provider_combo_ = new QComboBox;
  model_combo_ = new QComboBox;
  model_combo_->setEditable(true);
  model_combo_->setInsertPolicy(QComboBox::NoInsert);
  question_edit_ = new QLineEdit;
  question_edit_->setPlaceholderText(tr("e.g. Why is my LaserScan display empty?"));
  include_topic_check_ = new QCheckBox(tr("Include the topic selected on the Topic tab"));
  include_topic_check_->setChecked(true);
  ask_button_ = new QPushButton(tr("Ask AI"));
  ask_button_->setDefault(true);
  stop_button_ = new QPushButton(tr("Stop"));
  stop_button_->setEnabled(false);
  answer_status_ = new QLabel;
  answer_status_->setWordWrap(true);
  answer_view_ = new QTextBrowser;
  answer_view_->setOpenExternalLinks(true);
  answer_view_->setPlaceholderText(
    tr("The answer streams in here. It combines AutoDiag's rule-based findings, curated ROS 2 / DDS "
       "documentation and the selected model. Cloud models receive findings and your question only."));

  auto * ai_tab = new QWidget;
  auto * ai_layout = new QVBoxLayout(ai_tab);
  auto * model_form = new QFormLayout;
  model_form->addRow(tr("Provider"), provider_combo_);
  model_form->addRow(tr("Model"), model_combo_);
  ai_layout->addLayout(model_form);
  ai_layout->addWidget(question_edit_);
  ai_layout->addWidget(include_topic_check_);
  auto * ask_row = new QHBoxLayout;
  ask_row->addWidget(ask_button_);
  ask_row->addWidget(stop_button_);
  new_chat_button_ = new QPushButton(tr("New conversation"));
  new_chat_button_->setObjectName(QStringLiteral("newChat"));
  new_chat_button_->setToolTip(tr("Forget earlier questions and answers and start fresh"));
  ask_row->addWidget(new_chat_button_);
  ask_row->addStretch();
  ai_layout->addLayout(ask_row);
  ai_layout->addWidget(answer_status_);
  ai_layout->addWidget(answer_view_, 1);

  // Object names: stable handles for tests, scripts and style sheets.
  server_edit_->setObjectName(QStringLiteral("server"));
  token_edit_->setObjectName(QStringLiteral("token"));
  health_label_->setObjectName(QStringLiteral("health"));
  findings_list_->setObjectName(QStringLiteral("findings"));
  topic_combo_->setObjectName(QStringLiteral("topic"));
  inspect_button->setObjectName(QStringLiteral("inspect"));
  topic_view_->setObjectName(QStringLiteral("topicView"));
  provider_combo_->setObjectName(QStringLiteral("provider"));
  model_combo_->setObjectName(QStringLiteral("model"));
  question_edit_->setObjectName(QStringLiteral("question"));
  ask_button_->setObjectName(QStringLiteral("ask"));
  answer_status_->setObjectName(QStringLiteral("answerStatus"));
  answer_view_->setObjectName(QStringLiteral("answer"));

  tabs_ = new QTabWidget;
  tabs_->addTab(health_tab, tr("Health"));
  tabs_->addTab(topic_tab, tr("Topic"));
  tabs_->addTab(ai_tab, tr("AI assistant"));
  tabs_->addTab(buildConfigureTab(), tr("Configure RViz"));

  auto * layout = new QVBoxLayout(this);
  layout->addLayout(server_row);
  layout->addWidget(token_edit_);
  layout->addWidget(connection_label_);
  layout->addWidget(tabs_, 1);

  connect(connect_button, &QPushButton::clicked, this, &AutoDiagPanel::connectToServer);
  connect(server_edit_, &QLineEdit::returnPressed, this, &AutoDiagPanel::connectToServer);
  connect(dashboard_button, &QPushButton::clicked, this, &AutoDiagPanel::openDashboard);
  connect(refresh_button, &QPushButton::clicked, this, &AutoDiagPanel::refreshHealth);
  connect(auto_refresh_check_, &QCheckBox::toggled, this, [this](bool on) {
      if (on) {auto_refresh_timer_->start();} else {auto_refresh_timer_->stop();}
    });
  connect(auto_refresh_timer_, &QTimer::timeout, this, &AutoDiagPanel::refreshHealth);
  connect(topics_button, &QPushButton::clicked, this, &AutoDiagPanel::refreshTopics);
  connect(inspect_button, &QPushButton::clicked, this, &AutoDiagPanel::inspectTopic);
  connect(provider_combo_, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &AutoDiagPanel::loadModels);
  connect(ask_button_, &QPushButton::clicked, this, &AutoDiagPanel::ask);
  connect(question_edit_, &QLineEdit::returnPressed, this, &AutoDiagPanel::ask);
  connect(stop_button_, &QPushButton::clicked, this, &AutoDiagPanel::stopAsk);
  connect(new_chat_button_, &QPushButton::clicked, this, &AutoDiagPanel::newChat);
  // Mark the RViz config as modified when settings that are saved change.
  connect(server_edit_, &QLineEdit::editingFinished, this, [this]() {Q_EMIT configChanged();});
  connect(model_combo_, &QComboBox::currentTextChanged, this, [this]() {Q_EMIT configChanged();});
}

AutoDiagPanel::~AutoDiagPanel()
{
  if (stream_) {
    stream_->abort();
  }
}

void AutoDiagPanel::onInitialize()
{
  // Defer so RViz finishes loading displays (and this panel's config) first.
  QTimer::singleShot(0, this, &AutoDiagPanel::connectToServer);
}

void AutoDiagPanel::load(const rviz_common::Config & config)
{
  rviz_common::Panel::load(config);
  QString value;
  if (config.mapGetString("Server", &value) && !value.isEmpty()) {
    server_edit_->setText(value);
  }
  config.mapGetString("Provider", &wanted_provider_);
  config.mapGetString("Model", &wanted_model_);
  config.mapGetString("Topic", &wanted_topic_);
  bool include_topic = true;
  if (config.mapGetBool("IncludeTopic", &include_topic)) {
    include_topic_check_->setChecked(include_topic);
  }
  bool auto_refresh = false;
  if (config.mapGetBool("AutoRefresh", &auto_refresh)) {
    auto_refresh_check_->setChecked(auto_refresh);
  }
}

void AutoDiagPanel::save(rviz_common::Config config) const
{
  rviz_common::Panel::save(config);
  // The access token is deliberately not saved: RViz configs are plain files that get shared.
  config.mapSetValue("Server", server_edit_->text());
  config.mapSetValue("Provider", provider_combo_->currentData().toString());
  config.mapSetValue("Model", model_combo_->currentText());
  config.mapSetValue("Topic", selectedTopic());
  config.mapSetValue("IncludeTopic", include_topic_check_->isChecked());
  config.mapSetValue("AutoRefresh", auto_refresh_check_->isChecked());
}

// ------------------------------------------------------------------------------ networking

QNetworkRequest AutoDiagPanel::request(const QString & path, int timeout_ms) const
{
  QUrl url(server_edit_->text().trimmed().remove(QRegularExpression(QStringLiteral("/+$"))) + path);
  QNetworkRequest req(url);
  req.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/json"));
  req.setTransferTimeout(timeout_ms);
  const QString token = token_edit_->text().trimmed();
  if (!token.isEmpty()) {
    req.setRawHeader("Authorization", "Bearer " + token.toUtf8());
  }
  return req;
}

QNetworkReply * AutoDiagPanel::get(const QString & path, int timeout_ms)
{
  return net_->get(request(path, timeout_ms));
}

QNetworkReply * AutoDiagPanel::post(const QString & path, const QJsonObject & body, int timeout_ms)
{
  return net_->post(request(path, timeout_ms), QJsonDocument(body).toJson(QJsonDocument::Compact));
}

QString AutoDiagPanel::errorText(QNetworkReply * reply)
{
  const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
  const QString detail = parseObject(reply->readAll()).value(QStringLiteral("detail")).toString();
  if (!detail.isEmpty()) {
    return detail;
  }
  if (status == 401) {
    return tr("The server requires a token (AUTODIAG_UI_TOKEN).");
  }
  if (reply->error() == QNetworkReply::ConnectionRefusedError) {
    return tr("Cannot reach the AutoDiag server. Start it with: dds-autodiag serve");
  }
  if (reply->error() == QNetworkReply::OperationCanceledError) {
    return tr("Request timed out.");
  }
  return reply->errorString();
}

QString AutoDiagPanel::severityMark(const QString & severity)
{
  if (severity == QLatin1String("error")) {return QStringLiteral("✖");}
  if (severity == QLatin1String("warning")) {return QStringLiteral("▲");}
  return QStringLiteral("●");
}

void AutoDiagPanel::setConnection(const QString & text, const QString & color)
{
  connection_label_->setText(text);
  connection_label_->setStyleSheet(QStringLiteral("color: %1;").arg(color));
}

// ------------------------------------------------------------------------------ actions

void AutoDiagPanel::connectToServer()
{
  setConnection(tr("Connecting…"), QStringLiteral("gray"));
  QNetworkReply * reply = get(QStringLiteral("/api/version"), 5000);
  connect(reply, &QNetworkReply::finished, this, [this, reply]() {
      reply->deleteLater();
      if (reply->error() != QNetworkReply::NoError) {
        // RViz often starts before the server (e.g. from the launch file): keep trying for a short while.
        if (reply->error() == QNetworkReply::ConnectionRefusedError && connect_attempts_ < kConnectRetries) {
          ++connect_attempts_;
          setConnection(tr("Waiting for the AutoDiag server to start… (%1/%2)").arg(connect_attempts_).arg(kConnectRetries),
                        QStringLiteral("gray"));
          QTimer::singleShot(kConnectRetryMs, this, &AutoDiagPanel::connectToServer);
          return;
        }
        connect_attempts_ = 0;
        setConnection(errorText(reply), QStringLiteral("#c2304a"));
        return;
      }
      connect_attempts_ = 0;
      const QJsonObject info = parseObject(reply->readAll());
      setConnection(tr("Connected to AutoDiag %1").arg(info.value(QStringLiteral("version")).toString()),
                    QStringLiteral("#0f8a64"));
      refreshHealth();
      refreshTopics();
      loadProviders();
    });
}

void AutoDiagPanel::refreshHealth()
{
  health_label_->setText(tr("Checking ROS 2, network and container setup (a few seconds)…"));
  QNetworkReply * reply = get(QStringLiteral("/api/v09/overview"), 30000);
  connect(reply, &QNetworkReply::finished, this, [this, reply]() {
      reply->deleteLater();
      if (reply->error() != QNetworkReply::NoError) {
        health_label_->setText(errorText(reply));
        return;
      }
      const QJsonObject data = parseObject(reply->readAll());
      const QJsonObject health = data.value(QStringLiteral("health")).toObject();
      const QJsonObject summary = data.value(QStringLiteral("summary")).toObject();
      const QString status = health.value(QStringLiteral("status")).toString();
      const QString color = status == QLatin1String("issue_detected") ? QStringLiteral("#c2304a") :
        (status == QLatin1String("healthy") ? QStringLiteral("#0f8a64") : QStringLiteral("#a86400"));
      health_label_->setText(
        QStringLiteral("<b style='color:%1'>%2</b><br><small>%3 · ROS %4 · domain %5 · %6 nodes · %7 topics</small>")
        .arg(color, health.value(QStringLiteral("summary")).toString().toHtmlEscaped(),
        summary.value(QStringLiteral("host")).toString().toHtmlEscaped(),
        summary.value(QStringLiteral("ros_distro")).toString(QStringLiteral("?")),
        summary.value(QStringLiteral("domain_id")).toString(QStringLiteral("0")),
        summary.value(QStringLiteral("node_count")).toVariant().toString(),
        summary.value(QStringLiteral("topic_count")).toVariant().toString()));

      findings_list_->clear();
      const QJsonArray issues = data.value(QStringLiteral("issues")).toArray();
      if (issues.isEmpty()) {
        findings_list_->addItem(tr("✔ No rule matched. Inspect a topic to confirm data is actually delivered."));
      }
      for (const QJsonValue & value : issues) {
        const QJsonObject issue = value.toObject();
        auto * item = new QListWidgetItem(QStringLiteral("%1 %2 — %3").arg(
            severityMark(issue.value(QStringLiteral("severity")).toString()),
            issue.value(QStringLiteral("code")).toString(),
            issue.value(QStringLiteral("summary")).toString()));
        item->setToolTip(tr("Next step: %1").arg(issue.value(QStringLiteral("recommended_action")).toString()));
        findings_list_->addItem(item);
      }
    });
}

QStringList AutoDiagPanel::displayTopics() const
{
  QStringList problems;
  QStringList fine;
  if (!getDisplayContext()) {
    return {};
  }
  // Walk all displays, including nested display groups.
  std::function<void(rviz_common::DisplayGroup *)> walk = [&](rviz_common::DisplayGroup * group) {
      for (int i = 0; group && i < group->numDisplays(); ++i) {
        rviz_common::Display * display = group->getDisplayAt(i);
        if (auto * sub_group = dynamic_cast<rviz_common::DisplayGroup *>(display)) {
          walk(sub_group);
          continue;
        }
        rviz_common::properties::Property * topic_property = findProperty(display, QStringLiteral("Topic"));
        const QString topic = topic_property ? topic_property->getValue().toString() : QString();
        if (!topic.startsWith(QLatin1Char('/'))) {
          continue;
        }
        rviz_common::properties::StatusProperty * status = nullptr;
        for (int c = 0; c < display->numChildren() && !status; ++c) {
          auto * child = display->childAt(c);  // named "Status: Ok/Warn/Error"
          if (child && child->getName().startsWith(QLatin1String("Status"))) {
            status = dynamic_cast<rviz_common::properties::StatusProperty *>(child);
          }
        }
        const bool bad = display->isEnabled() && status &&
          status->getLevel() >= rviz_common::properties::StatusProperty::Warn;
        (bad ? problems : fine).append(topic);
      }
    };
  walk(getDisplayContext()->getRootDisplayGroup());
  problems.removeDuplicates();
  fine.removeDuplicates();
  for (const QString & topic : problems) {
    fine.removeAll(topic);
  }
  QStringList marked;
  for (const QString & topic : problems) {
    marked << QStringLiteral("⚠ ") + topic;
  }
  return marked + fine;
}

QString AutoDiagPanel::selectedTopic() const
{
  QString text = topic_combo_->currentText().trimmed();
  if (text.startsWith(QStringLiteral("⚠ "))) {
    text = text.mid(2);
  }
  const int bracket = text.indexOf(QLatin1String("  ["));  // "topic  [type]" entries
  return bracket > 0 ? text.left(bracket).trimmed() : text;
}

void AutoDiagPanel::refreshTopics()
{
  const QString keep = selectedTopic().isEmpty() ? wanted_topic_ : selectedTopic();
  QNetworkReply * reply = get(QStringLiteral("/api/topics"), 20000);
  connect(reply, &QNetworkReply::finished, this, [this, reply, keep]() {
      reply->deleteLater();
      const QStringList from_displays = displayTopics();
      topic_combo_->clear();
      for (const QString & topic : from_displays) {
        topic_combo_->addItem(topic + tr("  [RViz display]"));
      }
      if (reply->error() == QNetworkReply::NoError) {
        const QJsonArray topics = parseObject(reply->readAll()).value(QStringLiteral("topics")).toArray();
        for (const QJsonValue & value : topics) {
          const QJsonObject t = value.toObject();
          const QString name = t.value(QStringLiteral("topic")).toString();
          if (!from_displays.contains(name) && !from_displays.contains(QStringLiteral("⚠ ") + name)) {
            topic_combo_->addItem(name + QStringLiteral("  [") + t.value(QStringLiteral("type")).toString() + ']');
          }
        }
      } else {
        topic_view_->setPlainText(errorText(reply));
      }
      for (int i = 0; i < topic_combo_->count(); ++i) {
        if (topic_combo_->itemText(i).contains(keep) && !keep.isEmpty()) {
          topic_combo_->setCurrentIndex(i);
          break;
        }
      }
    });
}

void AutoDiagPanel::inspectTopic()
{
  const QString topic = selectedTopic();
  if (topic.isEmpty()) {
    topic_view_->setPlainText(tr("Pick or type a topic first."));
    return;
  }
  topic_view_->setPlainText(tr("Inspecting %1 …").arg(topic));
  QUrlQuery query;
  query.addQueryItem(QStringLiteral("topic"), topic);
  QNetworkReply * reply = get(QStringLiteral("/api/topic-inspect?") + query.toString(QUrl::FullyEncoded), 25000);
  connect(reply, &QNetworkReply::finished, this, [this, reply, topic]() {
      reply->deleteLater();
      if (reply->error() != QNetworkReply::NoError) {
        topic_view_->setPlainText(errorText(reply));
        return;
      }
      const QJsonObject data = parseObject(reply->readAll());
      if (data.value(QStringLiteral("state")).toString() != QLatin1String("ok")) {
        topic_view_->setPlainText(data.value(QStringLiteral("error")).toString());
        return;
      }
      QString html = QStringLiteral("<h3>%1</h3><p>%2 publisher(s), %3 subscriber(s)</p>")
        .arg(topic.toHtmlEscaped())
        .arg(data.value(QStringLiteral("publisher_count")).toInt())
        .arg(data.value(QStringLiteral("subscriber_count")).toInt());
      const QJsonArray findings = data.value(QStringLiteral("findings")).toArray();
      if (findings.isEmpty()) {
        html += tr("<p style='color:#0f8a64'>Advertised QoS is compatible. Delivery is not verified.</p>");
      }
      for (const QJsonValue & value : findings) {
        const QJsonObject f = value.toObject();
        html += QStringLiteral("<p style='color:#c2304a'><b>%1 %2</b><br>%3<br><i>%4</i></p>").arg(
          severityMark(f.value(QStringLiteral("severity")).toString()),
          f.value(QStringLiteral("code")).toString().toHtmlEscaped(),
          f.value(QStringLiteral("summary")).toString().toHtmlEscaped(),
          f.value(QStringLiteral("recommended_action")).toString().toHtmlEscaped());
      }
      html += QStringLiteral("<table border='1' cellspacing='0' cellpadding='3'>"
          "<tr><th>Role</th><th>Node</th><th>Reliability</th><th>Durability</th></tr>");
      for (const QJsonValue & value : data.value(QStringLiteral("endpoints")).toArray()) {
        const QJsonObject e = value.toObject();
        const QJsonObject qos = e.value(QStringLiteral("qos")).toObject();
        html += QStringLiteral("<tr><td>%1</td><td>%2</td><td>%3</td><td>%4</td></tr>").arg(
          e.value(QStringLiteral("kind")).toString(), e.value(QStringLiteral("node")).toString().toHtmlEscaped(),
          qos.value(QStringLiteral("reliability")).toString(), qos.value(QStringLiteral("durability")).toString());
      }
      html += QStringLiteral("</table>");
      topic_view_->setHtml(html);
    });
}

void AutoDiagPanel::loadProviders()
{
  QNetworkReply * reply = get(QStringLiteral("/api/ai/providers"), 10000);
  connect(reply, &QNetworkReply::finished, this, [this, reply]() {
      reply->deleteLater();
      if (reply->error() != QNetworkReply::NoError) {
        answer_status_->setText(errorText(reply));
        return;
      }
      const QJsonObject data = parseObject(reply->readAll());
      const QString keep = provider_combo_->count() ? provider_combo_->currentData().toString() :
        (wanted_provider_.isEmpty() ? data.value(QStringLiteral("default")).toString() : wanted_provider_);
      QSignalBlocker block(provider_combo_);
      provider_combo_->clear();
      for (const QJsonValue & value : data.value(QStringLiteral("providers")).toArray()) {
        const QJsonObject p = value.toObject();
        if (p.value(QStringLiteral("ready")).toBool()) {
          provider_combo_->addItem(p.value(QStringLiteral("label")).toString(), p.value(QStringLiteral("id")).toString());
        }
      }
      const int index = provider_combo_->findData(keep);
      provider_combo_->setCurrentIndex(index >= 0 ? index : 0);
      if (provider_combo_->count() == 0) {
        answer_status_->setText(tr("No AI provider is ready. Start Ollama or link an API key in the dashboard."));
      }
      loadModels();
      syncConfigureCombos();
    });
}

void AutoDiagPanel::loadModels()
{
  const QString provider = provider_combo_->currentData().toString();
  if (provider.isEmpty()) {
    return;
  }
  QNetworkReply * reply = get(QStringLiteral("/api/ai/providers/%1/models").arg(provider), 15000);
  connect(reply, &QNetworkReply::finished, this, [this, reply, provider]() {
      reply->deleteLater();
      if (reply->error() != QNetworkReply::NoError || provider != provider_combo_->currentData().toString()) {
        return;
      }
      const QJsonObject data = parseObject(reply->readAll());
      QString keep = wanted_model_.isEmpty() ? data.value(QStringLiteral("current")).toString() : wanted_model_;
      wanted_model_.clear();  // only applies to the first load after restoring the config
      model_combo_->clear();
      for (const QJsonValue & value : data.value(QStringLiteral("models")).toArray()) {
        model_combo_->addItem(value.toString());
      }
      if (!keep.isEmpty() && model_combo_->findText(keep) < 0) {
        model_combo_->insertItem(0, keep);
      }
      model_combo_->setCurrentText(keep);
      syncConfigureCombos();
    });
}

void AutoDiagPanel::ask()
{
  if (stream_) {
    return;
  }
  QJsonObject body;
  body.insert(QStringLiteral("question"), question_edit_->text().trimmed());
  body.insert(QStringLiteral("provider"), provider_combo_->currentData().toString());
  if (!model_combo_->currentText().trimmed().isEmpty()) {
    body.insert(QStringLiteral("model"), model_combo_->currentText().trimmed());
  }
  const QString topic = selectedTopic();
  if (include_topic_check_->isChecked() && topic.startsWith(QLatin1Char('/'))) {
    body.insert(QStringLiteral("topic"), topic);
  }
  // Earlier turns of this conversation (the server keeps the last few).
  body.insert(QStringLiteral("history"), chat_history_);
  pending_question_ = question_edit_->text().trimmed().isEmpty() ?
    tr("(Explain the current findings)") : question_edit_->text().trimmed();
  answer_.clear();
  sources_.clear();
  stream_buffer_.clear();
  got_first_token_ = false;
  renderAnswer();
  answer_status_->setText(tr("Collecting findings%1 and documentation…%2")
    .arg(body.contains(QStringLiteral("topic")) ? tr(" for %1").arg(topic) : QString())
    .arg(chat_history_.isEmpty() ? QString() : tr(" (follow-up, %n earlier message(s))", "", chat_history_.size())));
  ask_button_->setEnabled(false);
  stop_button_->setEnabled(true);
  stream_timer_.start();
  stream_ = post(QStringLiteral("/api/assistant/stream"), body, kStreamTimeoutMs);
  connect(stream_, &QNetworkReply::readyRead, this, &AutoDiagPanel::onStreamData);
  connect(stream_, &QNetworkReply::finished, this, &AutoDiagPanel::onStreamFinished);
}

void AutoDiagPanel::stopAsk()
{
  if (stream_) {
    stream_->abort();
  }
}

void AutoDiagPanel::onStreamData()
{
  if (!stream_ || stream_->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt() != 200) {
    return;  // error bodies are handled in onStreamFinished
  }
  stream_buffer_ += stream_->readAll();
  int newline;
  while ((newline = stream_buffer_.indexOf('\n')) >= 0) {
    const QByteArray line = stream_buffer_.left(newline).trimmed();
    stream_buffer_.remove(0, newline + 1);
    if (!line.isEmpty()) {
      handleStreamEvent(parseObject(line));
    }
  }
}

void AutoDiagPanel::handleStreamEvent(const QJsonObject & event)
{
  const QString type = event.value(QStringLiteral("type")).toString();
  if (type == QLatin1String("context")) {
    for (const QJsonValue & value : event.value(QStringLiteral("sources")).toArray()) {
      const QJsonObject s = value.toObject();
      sources_.insert(s.value(QStringLiteral("id")).toString(),
        {s.value(QStringLiteral("title")).toString(), s.value(QStringLiteral("url")).toString()});
    }
    answer_status_->setText(tr("%n finding(s) as context; waiting for the model…", "",
      event.value(QStringLiteral("issues")).toArray().size()));
  } else if (type == QLatin1String("meta")) {
    answer_model_ = event.value(QStringLiteral("label")).toString() + QStringLiteral(" · ") +
      event.value(QStringLiteral("model")).toString();
    answer_status_->setText(tr("%1 is writing…").arg(answer_model_));
  } else if (type == QLatin1String("thinking")) {
    answer_status_->setText(tr("%1 is reasoning before it answers (%2 characters)…")
      .arg(answer_model_).arg(event.value(QStringLiteral("chars")).toInt()));
  } else if (type == QLatin1String("token")) {
    got_first_token_ = true;
    answer_ += event.value(QStringLiteral("text")).toString();
    renderAnswer();
  } else if (type == QLatin1String("done")) {
    if (!answer_.trimmed().isEmpty()) {
      chat_history_.append(QJsonObject{{"role", "user"}, {"content", pending_question_}});
      chat_history_.append(QJsonObject{{"role", "assistant"}, {"content", answer_}});
      while (chat_history_.size() > 16) {chat_history_.removeFirst();}
      chat_transcript_ += QStringLiteral("**You:** %1\n\n**%2:**\n\n%3\n\n---\n\n")
        .arg(pending_question_, answer_model_, linkCitations(answer_));
      answer_.clear();
      pending_question_.clear();  // now part of the transcript
      renderAnswer();
      question_edit_->clear();
    }
    // Show the start of the newest answer.
    answer_view_->moveCursor(QTextCursor::End);
    answer_view_->find(QStringLiteral("You:"), QTextDocument::FindBackward);
    answer_status_->setText(tr("%1 · first words after %2 s · done in %3 s · advice only, trust the findings first")
      .arg(answer_model_)
      .arg(event.value(QStringLiteral("first_token_seconds")).toDouble(), 0, 'f', 1)
      .arg(event.value(QStringLiteral("seconds")).toDouble(), 0, 'f', 1));
  } else if (type == QLatin1String("error")) {
    answer_status_->setText(QStringLiteral("<span style='color:#c2304a'>%1</span>")
      .arg(event.value(QStringLiteral("message")).toString().toHtmlEscaped()));
  }
}

QString AutoDiagPanel::linkCitations(const QString & answer) const
{
  // Turn [doc-id] citations into links to the curated documentation.
  QString text = answer;
  static const QRegularExpression cite(QStringLiteral("\\[([a-z0-9-]+)\\](?!\\()"));
  QRegularExpressionMatchIterator it = cite.globalMatch(answer);
  QList<QRegularExpressionMatch> matches;
  while (it.hasNext()) {
    matches.prepend(it.next());
  }
  for (const QRegularExpressionMatch & m : matches) {
    const auto source = sources_.find(m.captured(1));
    if (source != sources_.end()) {
      text.replace(m.capturedStart(), m.capturedLength(),
        QStringLiteral("[%1](%2)").arg(source->first, source->second));
    }
  }
  return text;
}

void AutoDiagPanel::renderAnswer()
{
  QString text = chat_transcript_;
  if (!pending_question_.isEmpty() && (stream_ || !answer_.isEmpty())) {
    text += QStringLiteral("**You:** %1\n\n").arg(pending_question_);
    if (!answer_.isEmpty()) {
      text += QStringLiteral("**%1:**\n\n").arg(answer_model_) + linkCitations(answer_);
    }
  }
  answer_view_->setMarkdown(text);
  answer_view_->moveCursor(QTextCursor::End);
}

void AutoDiagPanel::newChat()
{
  stopAsk();
  chat_history_ = QJsonArray();
  chat_transcript_.clear();
  pending_question_.clear();
  answer_.clear();
  answer_view_->clear();
  answer_status_->setText(tr("New conversation."));
}

void AutoDiagPanel::onStreamFinished()
{
  QNetworkReply * reply = stream_;
  stream_ = nullptr;
  ask_button_->setEnabled(true);
  stop_button_->setEnabled(false);
  if (!reply) {
    return;
  }
  reply->deleteLater();
  if (reply->error() == QNetworkReply::OperationCanceledError) {
    // Both Stop and the transfer timeout surface as "canceled".
    answer_status_->setText(stream_timer_.elapsed() >= kStreamTimeoutMs - 1000 ?
      tr("The model took too long and was stopped.") : tr("Stopped."));
  } else if (reply->error() != QNetworkReply::NoError) {
    answer_status_->setText(QStringLiteral("<span style='color:#c2304a'>%1</span>")
      .arg(errorText(reply).toHtmlEscaped()));
  }
}

void AutoDiagPanel::openDashboard()
{
  QDesktopServices::openUrl(QUrl(server_edit_->text().trimmed() + QStringLiteral("/#assistant")));
}

}  // namespace rviz_autodiag_panel

PLUGINLIB_EXPORT_CLASS(rviz_autodiag_panel::AutoDiagPanel, rviz_common::Panel)
