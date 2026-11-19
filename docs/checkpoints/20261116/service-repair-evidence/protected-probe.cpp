/** @brief Protected finite Poco OP_MSG command-reset regression checks. */
#include <cstdlib>
#include <iostream>
#include <map>
#include <string>
#include <nlohmann/json.hpp>
#include "Poco/SharedPtr.h"
#include "Poco/MongoDB/Connection.h"
#include "Poco/MongoDB/Database.h"
#include "Poco/MongoDB/Document.h"
#include "Poco/MongoDB/OpMsgMessage.h"

int main(int argc, char** argv)
{
    if (argc != 2) return 2;
    const std::string databaseName{argv[1]};
    std::map<std::string, bool> cases;
    nlohmann::json observations;
    try
    {
        Poco::MongoDB::Connection connection{"127.0.0.1", 27017};
        Poco::MongoDB::Database database{databaseName};
        auto request = database.createOpMsgMessage("numbers");
        request->setCommandName(Poco::MongoDB::OpMsgMessage::CMD_INSERT);
        auto document = Poco::makeShared<Poco::MongoDB::Document>();
        document->add("number", 42);
        request->documents().push_back(document);
        Poco::MongoDB::OpMsgMessage response;
        connection.sendRequest(*request, response);
        cases["insert_before_reset"] = response.responseOk();
        observations["insert_response"] = response.body().toString();
        request->setCommandName(Poco::MongoDB::OpMsgMessage::CMD_DROP);
        cases["reset_drops_old_sequence"] = request->documents().empty();
        cases["reset_preserves_database"] = request->databaseName() == databaseName;
        cases["reset_preserves_collection"] = request->collectionName() == "numbers";
        cases["reset_selects_drop"] = request->commandName() == Poco::MongoDB::OpMsgMessage::CMD_DROP;
        connection.sendRequest(*request, response);
        cases["reused_drop_accepted"] = response.responseOk();
        observations["reused_drop_response"] = response.body().toString();
        auto fresh = database.createOpMsgMessage("numbers");
        fresh->setCommandName(Poco::MongoDB::OpMsgMessage::CMD_INSERT);
        fresh->documents().push_back(document);
        connection.sendRequest(*fresh, response);
        cases["fresh_insert_after_drop"] = response.responseOk();
        auto cleanup = database.createOpMsgMessage("numbers");
        cleanup->setCommandName(Poco::MongoDB::OpMsgMessage::CMD_DROP);
        connection.sendRequest(*cleanup, response);
        cases["fresh_drop_control"] = response.responseOk();
        observations["fresh_drop_response"] = response.body().toString();
    }
    catch (const std::exception& error)
    {
        observations["exception"] = error.what();
    }
    bool passed = cases.size() == 8;
    for (const auto& item : cases) passed = passed && item.second;
    // This standalone evidence probe emits its machine-readable result only.
    const auto raw = nlohmann::json{{"namespace", databaseName}, {"cases", cases}, {"observations", observations}}.dump();
    std::fwrite(raw.data(), 1, raw.size(), stdout);
    std::fputc('\n', stdout);
    return passed ? 0 : 1;
}
