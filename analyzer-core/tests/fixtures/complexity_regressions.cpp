// Synthetic regression fixture: each logical operator is one decision point.
bool logical_chain(bool first, bool second, bool third) {
    if (first && second && third) return true;
    return false;
}

bool alternative_chain(bool first, bool second, bool third) {
    if (first and second or third) return true;
    return false;
}

#define BOTH(first, second) ((first) && (second))
bool macro_chain(bool first, bool second, bool third) {
    if (BOTH(first, second) && third) return true;
    return false;
}
#undef BOTH

bool nested_comparison(bool first, bool second, bool third) {
    if ((first && second) == third) return true;
    return false;
}

bool bitwise_condition(bool first, bool second) {
    if (first & second) return true;
    return false;
}

int contains_lambda(bool first) {
    const auto callback = [](bool left, bool right) {
        if (left && right) return 1;
        return 0;
    };
    if (first) return 1;
    return callback(first, false);
}

template <typename Value>
bool template_branch(Value first, Value second, Value third) {
    if (first && second && third) return true;
    return false;
}

template <typename Value>
Value template_length(Value value) {
    Value result = value;
    return result;
}

template <typename Value>
Value template_parameters(Value first, Value second, Value third) {
    return first + second + third;
}

template <typename Value>
struct TemplateContainer {
    template <typename Other>
    bool member_template(Other first, Other second, Other third) {
        if (first && second && third) return true;
        return false;
    }
};

int lambda_capture_initializer(bool first, bool second) {
    const auto callback = [captured = first && second] { return captured; };
    return callback();
}

int contains_local_class() {
    struct Local {
        int nested_method(bool first, bool second) {
            if (first && second) return 1;
            return 0;
        }
    };
    return Local{}.nested_method(true, false);
}

int branchless_function() { return 1; }

template <typename Value>
Value declared_only(Value first, Value second);

struct LogicalOperand {};
bool operator&&(LogicalOperand, LogicalOperand);
bool overloaded_logical(LogicalOperand first, LogicalOperand second) {
    return first && second;
}

int nested_lambda_capture(bool first, bool second) {
    const auto callback = [captured = [&] {
        if (first && second) return 1;
        return 0;
    }()] { return captured; };
    return callback();
}

bool overloaded_lambda_capture(LogicalOperand first, LogicalOperand second) {
    const auto callback = [captured = first && second] { return captured; };
    return callback();
}

bool direct_lambda_capture(bool first, bool second) {
    const auto callback = [captured(first && second)] { return captured; };
    return callback();
}

int conditional_lambda_capture(bool first) {
    const auto callback = [captured = first ? 1 : 2] { return captured; };
    return callback();
}

bool lambda_default_argument() {
    const auto callback = [](bool value = true && false) { return value; };
    return callback();
}
