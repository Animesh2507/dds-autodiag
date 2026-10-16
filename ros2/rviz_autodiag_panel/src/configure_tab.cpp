// "Configure RViz" tab: the AI proposes display changes (validated by the AutoDiag server),
// the user reviews them as a checklist, and only checked items are applied. One-step Undo
// restores the display tree and Fixed Frame from before the last Apply.
#include "rviz_autodiag_panel/autodiag_panel.hpp"

#include <functional>
#include <string>
#include <vector>

#include <QColor>
#include <QComboBox>
#include <QFormLayout>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QLabel>
#include <QListWidget>
#include <QNetworkReply>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QRegularExpression>
#include <QScrollArea>
#include <QSignalBlocker>
#include <QTimer>
#include <QVBoxLayout>

#include <rviz_common/display.hpp>
#include <rviz_common/display_context.hpp>
#include <rviz_common/display_group.hpp>
#include <rviz_common/frame_manager_iface.hpp>
#include <rviz_common/properties/property.hpp>
#include <rviz_common/properties/status_property.hpp>

namespace rviz_autodiag_panel
{

using rviz_common::Display;
using rviz_common::DisplayGroup;
using rviz_common::properties::Property;

namespace
{
constexpr int kPlanTimeoutMs = 300000;   // local models on CPU need up to a minute or two
constexpr int kRetryIntervalMs = 1000;
constexpr int kRetryTicks = 30;          // properties created on first message: wait up to 30 s
constexpr int kMaxPropertiesPerDisplay = 40;

QString valueToString(const QVariant & value)
{
  switch (static_cast<QMetaType::Type>(value.type())) {
    case QMetaType::Bool:
      return value.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    case QMetaType::QColor: {
        const QColor c = value.value<QColor>();
        return QStringLiteral("%1; %2; %3").arg(c.red()).arg(c.green()).arg(c.blue());
      }
    default:
      return value.toString();
  }
}

void forEachDisplay(DisplayGroup * group, const std::function<void(Display *)> & visit)
{
  for (int i = 0; group && i < group->numDisplays(); ++i) {
    Display * display = group->getDisplayAt(i);
    if (auto * sub = dynamic_cast<DisplayGroup *>(display)) {
      forEachDisplay(sub, visit);
    } else if (display) {
      visit(display);
    }
  }
}

QString statusName(Display * display)
{
  rviz_common::properties::StatusProperty * status = nullptr;
  for (int i = 0; i < display->numChildren() && !status; ++i) {
    // RViz renames the status list to "Status: Ok/Warn/Error".
    Property * child = display->childAt(i);
    if (child && child->getName().startsWith(QLatin1String("Status"))) {
      status = dynamic_cast<rviz_common::properties::StatusProperty *>(child);
    }
  }
  if (!status) {return QStringLiteral("Unknown");}
  switch (status->getLevel()) {
    case rviz_common::properties::StatusProperty::Ok: return QStringLiteral("Ok");
    case rviz_common::properties::StatusProperty::Warn: return QStringLiteral("Warn");
    case rviz_common::properties::StatusProperty::Error: return QStringLiteral("Error");
  }
  return QStringLiteral("Unknown");
}
}  // namespace

QWidget * AutoDiagPanel::buildConfigureTab()
{
  rviz_request_ = new QPlainTextEdit;
  rviz_request_->setObjectName(QStringLiteral("rvizRequest"));
  rviz_request_->setPlaceholderText(
    tr("What should RViz show? e.g. Show the lidar point cloud colored by height in base_link, "
       "keep it light-weight. My LaserScan shows nothing."));
  rviz_request_->setMaximumHeight(80);
  plan_button_ = new QPushButton(tr("Plan changes"));
  plan_button_->setObjectName(QStringLiteral("plan"));
  apply_button_ = new QPushButton(tr("Apply checked"));
  apply_button_->setObjectName(QStringLiteral("apply"));
  apply_button_->setEnabled(false);
  undo_button_ = new QPushButton(tr("Undo"));
  undo_button_->setObjectName(QStringLiteral("undo"));
  undo_button_->setEnabled(false);
  undo_button_->setToolTip(tr("Restore the displays and Fixed Frame from before the last Apply"));
  // Same selection as the AI assistant tab: changing either one changes both.
  cfg_provider_combo_ = new QComboBox;
  cfg_provider_combo_->setObjectName(QStringLiteral("cfgProvider"));
  cfg_model_combo_ = new QComboBox;
  cfg_model_combo_->setObjectName(QStringLiteral("cfgModel"));
  cfg_model_combo_->setEditable(true);
  cfg_model_combo_->setInsertPolicy(QComboBox::NoInsert);
  cfg_speed_hint_ = new QLabel;
  cfg_speed_hint_->setWordWrap(true);
  cfg_speed_hint_->setStyleSheet(QStringLiteral("color: gray;"));
  plan_status_ = new QLabel(
    tr("AutoDiag checks every change against your topics, frames and display types; "
       "nothing changes until you press Apply."));
  plan_status_->setObjectName(QStringLiteral("planStatus"));
  plan_status_->setWordWrap(true);
  plan_status_->setTextInteractionFlags(Qt::TextSelectableByMouse);
  plan_list_ = new QListWidget;
  plan_list_->setObjectName(QStringLiteral("planList"));
  plan_list_->setWordWrap(true);
  retry_timer_ = new QTimer(this);
  retry_timer_->setInterval(kRetryIntervalMs);

  auto * tab = new QWidget;
  auto * layout = new QVBoxLayout(tab);
  auto * model_form = new QFormLayout;
  model_form->addRow(tr("Provider"), cfg_provider_combo_);
  model_form->addRow(tr("Model"), cfg_model_combo_);
  layout->addLayout(model_form);
  layout->addWidget(cfg_speed_hint_);
  layout->addWidget(rviz_request_);
  auto * row = new QHBoxLayout;
  row->addWidget(plan_button_);
  row->addWidget(apply_button_);
  row->addWidget(undo_button_);
  rviz_new_button_ = new QPushButton(tr("New conversation"));
  rviz_new_button_->setObjectName(QStringLiteral("rvizNew"));
  rviz_new_button_->setToolTip(tr("Forget earlier requests and plans; the current RViz state is always used"));
  row->addWidget(rviz_new_button_);
  row->addStretch();
  layout->addLayout(row);
  auto * status_scroll = new QScrollArea;
  status_scroll->setWidget(plan_status_);
  status_scroll->setWidgetResizable(true);
  status_scroll->setFrameShape(QFrame::NoFrame);
  status_scroll->setMaximumHeight(120);
  layout->addWidget(status_scroll);
  layout->addWidget(plan_list_, 1);

  connect(plan_button_, &QPushButton::clicked, this, &AutoDiagPanel::planRviz);
  connect(apply_button_, &QPushButton::clicked, this, &AutoDiagPanel::applyPlan);
  connect(undo_button_, &QPushButton::clicked, this, &AutoDiagPanel::undoPlan);
  connect(rviz_new_button_, &QPushButton::clicked, this, &AutoDiagPanel::newRvizConversation);
  connect(retry_timer_, &QTimer::timeout, this, &AutoDiagPanel::retryPending);
  // Keep both tabs on one provider/model selection.
  connect(provider_combo_, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &AutoDiagPanel::syncConfigureCombos);
  connect(model_combo_, &QComboBox::currentTextChanged, this, &AutoDiagPanel::syncConfigureCombos);
  connect(cfg_provider_combo_, QOverload<int>::of(&QComboBox::currentIndexChanged), this, [this](int index) {
      const int target = provider_combo_->findData(cfg_provider_combo_->itemData(index));
      if (target >= 0 && target != provider_combo_->currentIndex()) {
        provider_combo_->setCurrentIndex(target);  // reloads the model list, then syncs back
      }
    });
  connect(cfg_model_combo_, &QComboBox::currentTextChanged, this, [this](const QString & text) {
      if (text != model_combo_->currentText()) {
        model_combo_->setCurrentText(text);
      }
    });
  syncConfigureCombos();
  return tab;
}

void AutoDiagPanel::syncConfigureCombos()
{
  if (!cfg_provider_combo_) {
    return;
  }
  QSignalBlocker block_provider(cfg_provider_combo_);
  QSignalBlocker block_model(cfg_model_combo_);
  // Providers: rebuild only when the list changed.
  bool same = cfg_provider_combo_->count() == provider_combo_->count();
  for (int i = 0; same && i < provider_combo_->count(); ++i) {
    same = cfg_provider_combo_->itemData(i) == provider_combo_->itemData(i);
  }
  if (!same) {
    cfg_provider_combo_->clear();
    for (int i = 0; i < provider_combo_->count(); ++i) {
      cfg_provider_combo_->addItem(provider_combo_->itemText(i), provider_combo_->itemData(i));
    }
  }
  cfg_provider_combo_->setCurrentIndex(provider_combo_->currentIndex());
  // Models: same, and never reset text the user is typing.
  same = cfg_model_combo_->count() == model_combo_->count();
  for (int i = 0; same && i < model_combo_->count(); ++i) {
    same = cfg_model_combo_->itemText(i) == model_combo_->itemText(i);
  }
  if (!same) {
    cfg_model_combo_->clear();
    for (int i = 0; i < model_combo_->count(); ++i) {
      cfg_model_combo_->addItem(model_combo_->itemText(i));
    }
  }
  if (cfg_model_combo_->currentText() != model_combo_->currentText()) {
    cfg_model_combo_->setCurrentText(model_combo_->currentText());
  }
  const QString provider = provider_combo_->currentData().toString();
  cfg_speed_hint_->setText(provider.isEmpty() ?
    tr("No AI provider is ready. Start Ollama or link an API key in the AutoDiag dashboard.") :
    provider == QLatin1String("ollama") ?
    tr("Local model: runs on this machine, about 1–2 minutes per plan on a CPU.") :
    tr("Cloud model: a few seconds per plan. Sends display settings, topic names and frame names."));
}

// ------------------------------------------------------------------------------ RViz state

QJsonObject AutoDiagPanel::rvizState() const
{
  QJsonObject state;
  rviz_common::DisplayContext * context = getDisplayContext();
  if (!context) {
    return state;
  }
  state.insert(QStringLiteral("fixed_frame"), context->getFixedFrame());
  QJsonArray frames;
  if (context->getFrameManager()) {
    for (const std::string & frame : context->getFrameManager()->getAllFrameNames()) {
      frames.append(QString::fromStdString(frame));
    }
  }
  state.insert(QStringLiteral("frames"), frames);

  QJsonArray displays;
  forEachDisplay(context->getRootDisplayGroup(), [&displays](Display * display) {
      QJsonObject d;
      d.insert(QStringLiteral("name"), display->getName());
      d.insert(QStringLiteral("type"), display->getClassId());
      d.insert(QStringLiteral("enabled"), display->isEnabled());
      d.insert(QStringLiteral("status"), statusName(display));
      Property * topic_property = AutoDiagPanel::findProperty(display, QStringLiteral("Topic"));
      if (!topic_property) {
        topic_property = AutoDiagPanel::findProperty(display, QStringLiteral("Description Topic"));
      }
      const QString topic = topic_property ? topic_property->getValue().toString() : QString();
      d.insert(QStringLiteral("topic"), topic);
      // Current settings, two levels deep ("Topic/Reliability Policy").
      QJsonObject props;
      for (int i = 0; i < display->numChildren() && props.size() < kMaxPropertiesPerDisplay; ++i) {
        Property * child = display->childAt(i);
        if (!child || child->getName().startsWith(QLatin1String("Status"))) {continue;}
        const QVariant value = child->getValue();
        if (value.isValid() && !valueToString(value).isEmpty()) {
          props.insert(child->getName(), valueToString(value));
        }
        for (int j = 0; j < child->numChildren() && props.size() < kMaxPropertiesPerDisplay; ++j) {
          Property * grandchild = child->childAt(j);
          if (grandchild && grandchild->getValue().isValid()) {
            props.insert(child->getName() + '/' + grandchild->getName(), valueToString(grandchild->getValue()));
          }
        }
      }
      d.insert(QStringLiteral("properties"), props);
      displays.append(d);
    });
  state.insert(QStringLiteral("displays"), displays);
  return state;
}

Display * AutoDiagPanel::findDisplay(const QString & name) const
{
  Display * found = nullptr;
  if (getDisplayContext()) {
    forEachDisplay(getDisplayContext()->getRootDisplayGroup(), [&](Display * display) {
        if (!found && display->getName().compare(name, Qt::CaseInsensitive) == 0) {
          found = display;
        }
      });
  }
  return found;
}

Property * AutoDiagPanel::findProperty(Property * root, const QString & path)
{
  Property * current = root;
  for (const QString & part : path.split(QLatin1Char('/'), Qt::SkipEmptyParts)) {
    Property * next = nullptr;
    for (int pass = 0; pass < 2 && !next; ++pass) {  // exact match first, then case-insensitive
      for (int i = 0; current && i < current->numChildren(); ++i) {
        Property * child = current->childAt(i);
        if (child && child->getName().compare(part.trimmed(),
          pass ? Qt::CaseInsensitive : Qt::CaseSensitive) == 0)
        {
          next = child;
          break;
        }
      }
    }
    if (!next) {
      return nullptr;
    }
    current = next;
  }
  return current == root ? nullptr : current;
}

namespace
{
// Depth-first search for a setting by name anywhere under `root` (for paths the AI nested wrongly).
Property * findByName(Property * root, const QString & name)
{
  for (int i = 0; root && i < root->numChildren(); ++i) {
    Property * child = root->childAt(i);
    if (!child) {continue;}
    if (child->getName().compare(name, Qt::CaseInsensitive) == 0) {return child;}
    if (Property * found = findByName(child, name)) {return found;}
  }
  return nullptr;
}
}  // namespace

bool AutoDiagPanel::setPropertyFromString(Property * property, const QString & value, QString * error)
{
  const QVariant current = property->getValue();
  QVariant converted = value;
  bool ok = true;
  switch (static_cast<QMetaType::Type>(current.type())) {
    case QMetaType::Bool:
      converted = QStringList{"true", "1", "yes", "on"}.contains(value.trimmed().toLower());
      break;
    case QMetaType::Int:
    case QMetaType::UInt:
    case QMetaType::LongLong:
      converted = value.trimmed().toInt(&ok);
      break;
    case QMetaType::Float:
    case QMetaType::Double:
      converted = value.trimmed().toDouble(&ok);
      break;
    case QMetaType::QColor: {
        const QStringList parts = value.split(QRegularExpression(QStringLiteral("[;,\\s]+")), Qt::SkipEmptyParts);
        QColor color = parts.size() == 3 ?
          QColor(parts[0].toInt(), parts[1].toInt(), parts[2].toInt()) : QColor(value.trimmed());
        ok = color.isValid();
        converted = color;
        break;
      }
    default:
      break;
  }
  if (!ok) {
    *error = tr("\"%1\" is not a valid value for %2").arg(value, property->getName());
    return false;
  }
  if (!property->setValue(converted) &&
    valueToString(property->getValue()).compare(valueToString(converted), Qt::CaseInsensitive) != 0)
  {
    *error = tr("RViz rejected value \"%1\" for %2").arg(value, property->getName());
    return false;
  }
  return true;  // also when the value was already set
}

// ------------------------------------------------------------------------------ planning

void AutoDiagPanel::planRviz()
{
  const QString request_text = rviz_request_->toPlainText().trimmed();
  if (request_text.isEmpty()) {
    plan_status_->setText(tr("Describe what you want RViz to show first."));
    return;
  }
  if (!getDisplayContext()) {
    plan_status_->setText(tr("This tab only works inside RViz."));
    return;
  }
  QJsonObject body = rvizState();
  body.insert(QStringLiteral("request"), request_text);
  body.insert(QStringLiteral("provider"), provider_combo_->currentData().toString());
  if (!model_combo_->currentText().trimmed().isEmpty()) {
    body.insert(QStringLiteral("model"), model_combo_->currentText().trimmed());
  }
  body.insert(QStringLiteral("history"), rviz_history_);
  plan_list_->clear();
  plan_actions_ = QJsonArray();
  apply_button_->setEnabled(false);
  plan_button_->setEnabled(false);
  const bool local = provider_combo_->currentData().toString() == QLatin1String("ollama");
  plan_status_->setText(local ?
    tr("Planning with the local model (about a minute on CPU)…") : tr("Planning…"));

  QNetworkReply * reply = post(QStringLiteral("/api/rviz/plan"), body, kPlanTimeoutMs);
  connect(reply, &QNetworkReply::finished, this, [this, reply, request_text]() {
      reply->deleteLater();
      plan_button_->setEnabled(true);
      if (reply->error() != QNetworkReply::NoError) {
        plan_status_->setText(QStringLiteral("<span style='color:#c2304a'>%1</span>")
          .arg(errorText(reply).toHtmlEscaped()));
        return;
      }
      const QJsonObject plan = QJsonDocument::fromJson(reply->readAll()).object();
      plan_actions_ = plan.value(QStringLiteral("actions")).toArray();
      // Record this turn; results are filled in when the plan is applied.
      QJsonArray turn_actions;
      for (const QJsonValue & value : plan_actions_) {
        turn_actions.append(QJsonObject{{"description", value.toObject().value(QStringLiteral("description"))},
          {"result", "proposed, not applied"}});
      }
      rviz_history_.append(QJsonObject{{"request", request_text}, {"summary", plan.value(QStringLiteral("summary"))},
        {"notes", plan.value(QStringLiteral("notes"))}, {"actions", turn_actions}});
      while (rviz_history_.size() > 6) {
        rviz_history_.removeFirst();
        applied_turn_ = applied_turn_ > 0 ? applied_turn_ - 1 : -1;
      }
      rviz_turn_ = rviz_history_.size() - 1;
      rviz_request_->clear();
      rviz_request_->setPlaceholderText(tr("Follow up, e.g. \"make the points bigger\" or \"use the other topic\"…"));
      QString text = rviz_history_.size() > 1 ?
        tr("<small>Follow-up %1 · you asked: %2</small><br>").arg(rviz_history_.size()).arg(request_text.toHtmlEscaped()) :
        tr("<small>You asked: %1</small><br>").arg(request_text.toHtmlEscaped());
      text += QStringLiteral("<b>%1</b>").arg(
        plan.value(QStringLiteral("summary")).toString().toHtmlEscaped());
      for (const QJsonValue & note : plan.value(QStringLiteral("notes")).toArray()) {
        text += QStringLiteral("<br>• ") + note.toString().toHtmlEscaped();
      }
      const QJsonArray rejected = plan.value(QStringLiteral("rejected")).toArray();
      if (!rejected.isEmpty()) {
        text += tr("<br><span style='color:#a86400'>Skipped %n invalid suggestion(s):</span>", "", rejected.size());
        for (const QJsonValue & r : rejected) {
          text += QStringLiteral("<br>&nbsp;&nbsp;– ") + r.toObject().value(QStringLiteral("reason")).toString().toHtmlEscaped();
        }
      }
      text += QStringLiteral("<br><small>%1 · %2 · %3 s</small>").arg(
        plan.value(QStringLiteral("provider")).toString(), plan.value(QStringLiteral("model")).toString(),
        QString::number(plan.value(QStringLiteral("seconds")).toDouble(), 'f', 1));
      plan_status_->setText(text);

      for (const QJsonValue & value : plan_actions_) {
        const QJsonObject action = value.toObject();
        auto * item = new QListWidgetItem(action.value(QStringLiteral("description")).toString());
        item->setFlags(item->flags() | Qt::ItemIsUserCheckable);
        item->setCheckState(action.value(QStringLiteral("unchecked")).toBool() ? Qt::Unchecked : Qt::Checked);
        if (action.value(QStringLiteral("auto")).toBool()) {
          item->setToolTip(tr("Added by AutoDiag's own checks, not by the AI model."));
        }
        plan_list_->addItem(item);
      }
      if (plan_actions_.isEmpty()) {
        plan_list_->addItem(tr("No changes proposed. Try describing the result you want more concretely."));
      }
      apply_button_->setEnabled(!plan_actions_.isEmpty());
    });
}

// ------------------------------------------------------------------------------ applying

void AutoDiagPanel::setTurnActionResult(int row, const QString & result)
{
  if (rviz_turn_ < 0 || rviz_turn_ >= rviz_history_.size()) {return;}
  QJsonObject turn = rviz_history_.at(rviz_turn_).toObject();
  QJsonArray actions = turn.value(QStringLiteral("actions")).toArray();
  if (row >= actions.size()) {return;}
  QJsonObject action = actions.at(row).toObject();
  action.insert(QStringLiteral("result"), result);
  actions.replace(row, action);
  turn.insert(QStringLiteral("actions"), actions);
  rviz_history_.replace(rviz_turn_, turn);
}

void AutoDiagPanel::setActionResult(int row, const QString & mark, const QString & message)
{
  // Remember what really happened, so follow-up requests know it.
  if (mark == QStringLiteral("✔")) {
    setTurnActionResult(row, QStringLiteral("applied"));
  } else if (mark == QStringLiteral("–")) {
    setTurnActionResult(row, QStringLiteral("skipped by the user"));
  } else if (mark == QStringLiteral("✖")) {
    setTurnActionResult(row, QStringLiteral("failed (") + message + ')');
  } else {
    setTurnActionResult(row, QStringLiteral("waiting for data"));
  }
  QListWidgetItem * item = plan_list_->item(row);
  if (!item) {return;}
  const QString description = plan_actions_.at(row).toObject().value(QStringLiteral("description")).toString();
  item->setText(mark + QLatin1Char(' ') + description + (message.isEmpty() ? QString() : QStringLiteral(" — ") + message));
  item->setFlags(item->flags() & ~Qt::ItemIsUserCheckable);
  item->setData(Qt::CheckStateRole, QVariant());  // remove the checkbox once applied
}

QString AutoDiagPanel::applyAction(const QJsonObject & a)
{
  rviz_common::DisplayContext * context = getDisplayContext();
  DisplayGroup * root = context->getRootDisplayGroup();
  const QString kind = a.value(QStringLiteral("action")).toString();
  const QString name = a.value(QStringLiteral("display")).toString();

  if (kind == QLatin1String("set_fixed_frame")) {
    Property * frame = findProperty(root, QStringLiteral("Global Options/Fixed Frame"));
    if (!frame) {return tr("Fixed Frame setting not found");}
    QString error;
    return setPropertyFromString(frame, a.value(QStringLiteral("frame")).toString(), &error) ? QString() : error;
  }
  if (kind == QLatin1String("add_display")) {
    Display * display = root->createDisplay(a.value(QStringLiteral("class_id")).toString());
    if (!display) {return tr("RViz could not create this display type");}
    root->addDisplay(display);
    display->initialize(context);
    display->setName(name);
    display->setEnabled(true);
    const QString topic = a.value(QStringLiteral("topic")).toString();
    const QString topic_property = a.value(QStringLiteral("topic_property")).toString();
    if (!topic.isEmpty() && !topic_property.isEmpty()) {
      Property * property = findProperty(display, topic_property);
      if (!property) {return tr("created, but it has no \"%1\" setting").arg(topic_property);}
      property->setValue(topic);
    }
    return QString();
  }

  Display * display = findDisplay(name);
  if (!display) {return tr("display \"%1\" not found").arg(name);}
  if (kind == QLatin1String("remove_display")) {
    if (auto * parent = dynamic_cast<DisplayGroup *>(display->getParent())) {
      parent->takeDisplay(display);
    }
    display->disconnect();  // as RViz's Displays panel does before deleting
    display->deleteLater();
    return QString();
  }
  if (kind == QLatin1String("set_enabled")) {
    display->setEnabled(a.value(QStringLiteral("value")).toString() == QLatin1String("true"));
    return QString();
  }
  if (kind == QLatin1String("rename_display")) {
    display->setName(a.value(QStringLiteral("value")).toString());
    return QString();
  }
  const QString path = kind == QLatin1String("set_topic") ?
    a.value(QStringLiteral("topic_property")).toString(QStringLiteral("Topic")) :
    a.value(QStringLiteral("property")).toString();
  const QString value = kind == QLatin1String("set_topic") ?
    a.value(QStringLiteral("topic")).toString() : a.value(QStringLiteral("value")).toString();
  Property * property = findProperty(display, path.isEmpty() ? QStringLiteral("Topic") : path);
  if (!property && path.contains(QLatin1Char('/'))) {
    property = findByName(display, path.section(QLatin1Char('/'), -1).trimmed());
  }
  if (!property) {
    // Some settings (e.g. a point cloud's "Axis") only exist once data has arrived.
    return QStringLiteral("pending:") + tr("waiting for \"%1\" to appear (it shows up once data arrives)").arg(path);
  }
  QString error;
  return setPropertyFromString(property, value, &error) ? QString() : error;
}

void AutoDiagPanel::applyPlan()
{
  rviz_common::DisplayContext * context = getDisplayContext();
  if (!context || plan_actions_.isEmpty()) {
    return;
  }
  // Snapshot for Undo: the whole display tree, including Global Options (Fixed Frame).
  undo_config_ = rviz_common::Config();
  context->getRootDisplayGroup()->save(undo_config_);
  has_undo_ = true;
  applied_turn_ = rviz_turn_;
  undo_button_->setEnabled(true);
  apply_button_->setEnabled(false);
  pending_rows_.clear();

  int applied = 0, failed = 0;
  for (int row = 0; row < plan_actions_.size(); ++row) {
    QListWidgetItem * item = plan_list_->item(row);
    if (!item || item->checkState() != Qt::Checked) {
      setActionResult(row, QStringLiteral("–"), tr("skipped"));
      continue;
    }
    const QString result = applyAction(plan_actions_.at(row).toObject());
    if (result.isEmpty()) {
      setActionResult(row, QStringLiteral("✔"), QString());
      ++applied;
    } else if (result.startsWith(QLatin1String("pending:"))) {
      setActionResult(row, QStringLiteral("⏳"), result.mid(8));
      pending_rows_.append(row);
    } else {
      setActionResult(row, QStringLiteral("✖"), result);
      ++failed;
    }
  }
  context->queueRender();
  Q_EMIT configChanged();
  plan_status_->setText(plan_status_->text() + tr("<br><b>Applied %1, failed %2%3.</b> Use File → Save Config to keep it.")
    .arg(applied).arg(failed)
    .arg(pending_rows_.isEmpty() ? QString() : tr(", waiting on %1").arg(pending_rows_.size())));
  if (!pending_rows_.isEmpty()) {
    retry_ticks_ = 0;
    retry_timer_->start();
  }
}

void AutoDiagPanel::retryPending()
{
  ++retry_ticks_;
  QList<int> still_pending;
  for (int row : pending_rows_) {
    const QString result = applyAction(plan_actions_.at(row).toObject());
    if (result.isEmpty()) {
      setActionResult(row, QStringLiteral("✔"), tr("applied once data arrived"));
    } else if (result.startsWith(QLatin1String("pending:")) && retry_ticks_ < kRetryTicks) {
      still_pending.append(row);
    } else {
      setActionResult(row, QStringLiteral("✖"), result.startsWith(QLatin1String("pending:")) ?
        tr("setting never appeared; is data arriving on the topic?") : result);
    }
  }
  pending_rows_ = still_pending;
  if (pending_rows_.isEmpty()) {
    retry_timer_->stop();
    if (getDisplayContext()) {getDisplayContext()->queueRender();}
  }
}

void AutoDiagPanel::undoPlan()
{
  rviz_common::DisplayContext * context = getDisplayContext();
  if (!context || !has_undo_) {
    return;
  }
  retry_timer_->stop();
  pending_rows_.clear();
  DisplayGroup * root = context->getRootDisplayGroup();
  root->removeAllDisplays();
  root->load(undo_config_);  // recreates displays and restores Global Options
  has_undo_ = false;
  undo_button_->setEnabled(false);
  context->queueRender();
  Q_EMIT configChanged();
  if (applied_turn_ >= 0 && applied_turn_ < rviz_history_.size()) {
    QJsonObject turn = rviz_history_.at(applied_turn_).toObject();
    turn.insert(QStringLiteral("undone"), true);
    rviz_history_.replace(applied_turn_, turn);
  }
  plan_status_->setText(tr("Restored the displays from before the last Apply."));
}

void AutoDiagPanel::newRvizConversation()
{
  rviz_history_ = QJsonArray();
  rviz_turn_ = -1;
  applied_turn_ = -1;
  plan_list_->clear();
  plan_actions_ = QJsonArray();
  apply_button_->setEnabled(false);
  rviz_request_->setPlaceholderText(
    tr("What should RViz show? e.g. Show the lidar point cloud colored by height in base_link."));
  plan_status_->setText(tr("New conversation. Earlier requests are forgotten; the current RViz state is still used."));
}

}  // namespace rviz_autodiag_panel
