// RViz2 panel for DDS AutoDiag.
//
// A thin client of the AutoDiag server (dds-autodiag serve): all diagnostics, documentation
// retrieval and AI providers (and their API keys) stay on the server. The panel adds RViz
// context: the topics used by the current displays, with displays in error listed first.
#pragma once

#include <QElapsedTimer>
#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QNetworkRequest>
#include <QPointer>
#include <QString>

#include <rviz_common/config.hpp>
#include <rviz_common/panel.hpp>

class QCheckBox;
class QComboBox;
class QGraphicsScene;
class QGraphicsView;
class QLabel;
class QLineEdit;
class QListWidget;
class QNetworkAccessManager;
class QNetworkReply;
class QPlainTextEdit;
class QPushButton;
class QTabWidget;
class QTextBrowser;
class QTimer;

namespace rviz_common
{
class Display;
namespace properties
{
class Property;
}
}  // namespace rviz_common

namespace rviz_autodiag_panel
{

class AutoDiagPanel : public rviz_common::Panel
{
  Q_OBJECT

public:
  explicit AutoDiagPanel(QWidget * parent = nullptr);
  ~AutoDiagPanel() override;

  void onInitialize() override;

  /// Child property by "Parent/Child" path without RViz's "Undefined property" logging; nullptr if absent.
  static rviz_common::properties::Property * findProperty(
    rviz_common::properties::Property * root, const QString & path);
  void load(const rviz_common::Config & config) override;
  void save(rviz_common::Config config) const override;

private Q_SLOTS:
  void connectToServer();
  void refreshHealth();
  void refreshTopics();
  void inspectTopic();
  void loadProviders();
  void loadModels();
  void ask();
  void stopAsk();
  void openDashboard();
  void onStreamData();
  void onStreamFinished();
  // "Graph" tab (graph_tab.cpp)
  void loadGraph();
  // "Configure RViz" tab (configure_tab.cpp)
  void planRviz();
  void applyPlan();
  void undoPlan();
  void retryPending();
  void newChat();
  void newRvizConversation();

private:
  QNetworkRequest request(const QString & path, int timeout_ms) const;
  QNetworkReply * get(const QString & path, int timeout_ms = 20000);
  QNetworkReply * post(const QString & path, const QJsonObject & body, int timeout_ms);
  static QString errorText(QNetworkReply * reply);
  static QString severityMark(const QString & severity);

  /// Topics referenced by RViz displays ("Topic" property), displays with errors first.
  QStringList displayTopics() const;
  QString selectedTopic() const;
  void setConnection(const QString & text, const QString & color);
  void handleStreamEvent(const QJsonObject & event);
  void renderAnswer();
  QString linkCitations(const QString & answer) const;

  // Connection
  QLineEdit * server_edit_;
  QLineEdit * token_edit_;
  QLabel * connection_label_;
  QTabWidget * tabs_;
  int connect_attempts_{0};

  // Health tab
  QLabel * health_label_;
  QListWidget * findings_list_;
  QCheckBox * auto_refresh_check_;
  QTimer * auto_refresh_timer_;

  // Topic tab
  QComboBox * topic_combo_;
  QTextBrowser * topic_view_;

  // AI tab
  QComboBox * provider_combo_;
  QComboBox * model_combo_;
  QLineEdit * question_edit_;
  QCheckBox * include_topic_check_;
  QPushButton * ask_button_;
  QPushButton * stop_button_;
  QLabel * answer_status_;
  QTextBrowser * answer_view_;

  QNetworkAccessManager * net_;
  QPointer<QNetworkReply> stream_;
  QByteArray stream_buffer_;
  QString answer_;
  QString answer_model_;
  QHash<QString, QPair<QString, QString>> sources_;  // id -> (title, url)
  QElapsedTimer stream_timer_;
  bool got_first_token_{false};

  // Conversation memory (session only, never written to disk).
  QJsonArray chat_history_;        // [{role, content}] for the AI assistant tab
  QString chat_transcript_;        // rendered earlier turns (Markdown)
  QString pending_question_;
  QPushButton * new_chat_button_{nullptr};
  QJsonArray rviz_history_;        // [{request, summary, notes, actions:[{description, result}], undone}]
  int rviz_turn_{-1};              // turn whose plan is shown in the list
  int applied_turn_{-1};           // turn that Undo would revert
  QPushButton * rviz_new_button_{nullptr};
  void setTurnActionResult(int row, const QString & result);

  // Restored from the RViz config before the server lists are loaded.
  QString wanted_provider_;
  QString wanted_model_;
  QString wanted_topic_;

  // "Graph" tab (graph_tab.cpp): every publisher -> subscriber connection, from GET /api/graph
  QWidget * buildGraphTab();
  void drawGraph(const QJsonObject & data);
  void showEdgeDetails(const QJsonObject & edge);
  void showWaitingDetails(const QJsonObject & waiting);
  QPushButton * graph_button_{nullptr};
  QLabel * graph_summary_{nullptr};
  QGraphicsScene * graph_scene_{nullptr};
  QGraphicsView * graph_view_{nullptr};
  QTextBrowser * graph_details_{nullptr};
  bool graph_loaded_{false};

  // "Configure RViz" tab (configure_tab.cpp)
  QWidget * buildConfigureTab();
  QJsonObject rvizState() const;
  rviz_common::Display * findDisplay(const QString & name) const;

  static bool setPropertyFromString(
    rviz_common::properties::Property * property, const QString & value, QString * error);
  /// Apply one action; returns "" on success, "pending:<reason>" to retry later, or an error.
  QString applyAction(const QJsonObject & action);
  void setActionResult(int row, const QString & mark, const QString & message);

  /// Mirror the AI tab's provider/model choice into the Configure tab (and back); one shared selection.
  void syncConfigureCombos();
  QComboBox * cfg_provider_combo_{nullptr};
  QComboBox * cfg_model_combo_;
  QLabel * cfg_speed_hint_;
  QPlainTextEdit * rviz_request_;
  QPushButton * plan_button_;
  QPushButton * apply_button_;
  QPushButton * undo_button_;
  QLabel * plan_status_;
  QListWidget * plan_list_;
  QJsonArray plan_actions_;
  rviz_common::Config undo_config_;
  bool has_undo_{false};
  QTimer * retry_timer_;
  QList<int> pending_rows_;
  int retry_ticks_{0};
};

}  // namespace rviz_autodiag_panel
