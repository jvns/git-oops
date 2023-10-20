import curses
import time


class CursesApp:
    def __init__(self):
        self.items = ["Item 1", "Item 2", "Item 3", "Item 4"]
        self.current_item = 0
        self.stdscr = None
        self.left_win = None
        self.right_win = None

    def run(self, stdscr):
        self.stdscr = stdscr
        self.setup_curses()
        self.main_loop()

    def setup_curses(self):
        curses.curs_set(0)
        self.stdscr.nodelay(1)
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)
        self.update_windows()

    def main_loop(self):
        while True:
            self.draw_items()
            self.draw_details()

            self.left_win.refresh()
            self.right_win.refresh()

            self.handle_input()

    def update_windows(self):
        max_y, max_x = self.stdscr.getmaxyx()
        center_x = max_x // 2

        if self.left_win:
            del self.left_win  # Delete the previous window object to avoid memory leak
        self.left_win = self.stdscr.subwin(max_y, center_x, 0, 0)
        self.left_win.box()

        if self.right_win:
            del self.right_win
        self.right_win = self.stdscr.subwin(max_y, max_x - center_x, 0, center_x)
        self.right_win.box()

    def draw_items(self):
        self.left_win.clear()
        self.left_win.box()  # Re-draw box after clearing
        for index, item in enumerate(self.items):
            if index == self.current_item:
                self.left_win.addstr(
                    index + 1, 1, item, curses.color_pair(1)
                )  # +1 to account for box's border
            else:
                self.left_win.addstr(index + 1, 1, item)

    def draw_details(self):
        self.right_win.clear()
        self.right_win.box()  # Re-draw box after clearing
        self.right_win.addstr(
            1, 1, f"Details for {self.items[self.current_item]}"
        )  # +1 to account for box's border

    def handle_input(self):
        key = self.stdscr.getch()

        if key == -1:
            # No input
            time.sleep(0.01)  # Sleep briefly to prevent 100% CPU usage
        elif key == ord("q"):
            exit()
        elif key == curses.KEY_UP and self.current_item > 0:
            self.current_item -= 1
        elif key == curses.KEY_DOWN and self.current_item < len(self.items) - 1:
            self.current_item += 1
        elif key == curses.KEY_RESIZE:
            self.update_windows()  # Recalculate window dimensions and redraw


if __name__ == "__main__":
    app = CursesApp()
    curses.wrapper(app.run)
