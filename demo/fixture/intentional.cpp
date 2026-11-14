// Synthetic analyzer inputs; intentional rule triggers, never executed.
typedef int Counter;
enum Mode { idle, active };
int exercise(double value) {
    int* owned = new int(1);
    int narrowed = (int)value;
    delete owned;
    return narrowed;
}
