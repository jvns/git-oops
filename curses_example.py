import curses
import time


def main(stdscr):
    # Setup the curses environment
    curses.curs_set(0)  # Hide the cursor
    stdscr.nodelay(1)  # Do not wait for user input when refreshing the screen
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Setup a color pair

    # Calculate window dimensions
    max_y, max_x = stdscr.getmaxyx()
    center_x = max_x // 2
    left_win = stdscr.subwin(max_y, center_x, 0, 0)  # Create the left window
    right_win = stdscr.subwin(
        max_y, max_x - center_x, 0, center_x
    )  # Create the right window

    items = ["Item 1", "Item 2", "Item 3", "Item 4"]  # Example items
    current_item = 0  # Currently selected item

    while True:
        # Clear the windows to prepare for new content
        left_win.clear()
        left_win.box()
        right_win.clear()
        right_win.box()

        # Draw the items on the left window
        for index, item in enumerate(items):
            if index == current_item:
                left_win.addstr(
                    index, 1, item, curses.color_pair(1)
                )  # Highlight the selected item
            else:
                left_win.addstr(index, 1, item)

        # Update the right window based on the selected item
        right_win.addstr(0, 1, f"Details for {items[current_item]}")

        # Refresh the windows to display changes
        left_win.refresh()
        right_win.refresh()

        time.sleep(0.1)  # Sleep for a bit to avoid 100% CPU usage
        # Capture user's key press
        key = stdscr.getch()

        # If the user presses 'q', quit the program
        if key == ord("q"):
            break

        # Allow the user to navigate through the items
        if key == curses.KEY_UP and current_item > 0:
            current_item -= 1
        elif key == curses.KEY_DOWN and current_item < len(items) - 1:
            current_item += 1


# Run the curses application
curses.wrapper(main)
