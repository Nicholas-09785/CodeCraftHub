# app.py

"""
A simple Flask REST API for managing courses.

The API stores all course data in a local JSON file named courses.json.

Install Flask with:
    pip install Flask

Run the application with:
    python app.py
"""

import json
import os
import threading
from datetime import datetime

from flask import Flask, jsonify, request


# Create the Flask application
app = Flask(__name__)

# Store courses.json in the same directory as this Python file
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "courses.json")

# Allowed values for a course's status
ALLOWED_STATUSES = {
    "Not Started",
    "In Progress",
    "Completed",
}

# A lock helps prevent two requests from writing to the JSON file at the same time
file_lock = threading.Lock()


class FileStorageError(Exception):
    """Custom exception used when the courses file cannot be read or written."""


def initialize_data_file():
    """
    Create courses.json automatically if it does not already exist.

    The file starts with an empty JSON list.
    """
    if not os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as file:
                json.dump([], file, indent=4)
        except OSError as error:
            raise FileStorageError(
                f"Unable to create the data file: {error}"
            ) from error


def load_courses():
    """
    Read and return all courses from courses.json.

    Returns:
        list: A list of course dictionaries.

    Raises:
        FileStorageError: If the file cannot be read or contains invalid JSON.
    """
    initialize_data_file()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            file_contents = file.read().strip()

            # Treat an empty file as an empty list
            if not file_contents:
                return []

            courses = json.loads(file_contents)

            # Make sure the JSON file contains a list
            if not isinstance(courses, list):
                raise FileStorageError(
                    "The data file must contain a JSON list."
                )

            return courses

    except json.JSONDecodeError as error:
        raise FileStorageError(
            f"The data file contains invalid JSON: {error}"
        ) from error
    except OSError as error:
        raise FileStorageError(
            f"Unable to read the data file: {error}"
        ) from error


def save_courses(courses):
    """
    Save all courses to courses.json.

    Args:
        courses (list): The list of course dictionaries.

    Raises:
        FileStorageError: If the file cannot be written.
    """
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as file:
            json.dump(courses, file, indent=4)
    except OSError as error:
        raise FileStorageError(
            f"Unable to write to the data file: {error}"
        ) from error


def get_next_course_id(courses):
    """
    Generate the next course ID.

    IDs start at 1. The next ID is one greater than the largest existing ID.
    This prevents deleted IDs from being reused.
    """
    if not courses:
        return 1

    return max(course.get("id", 0) for course in courses) + 1


def validate_date(target_date):
    """
    Validate that a date uses the YYYY-MM-DD format and is a real date.

    Returns:
        bool: True if valid, otherwise False.
    """
    if not isinstance(target_date, str):
        return False

    try:
        datetime.strptime(target_date, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_required_fields(data):
    """
    Check that all required fields exist and contain non-empty values.

    Returns:
        str or None: An error message if validation fails, otherwise None.
    """
    required_fields = [
        "name",
        "description",
        "target_date",
        "status",
    ]

    for field in required_fields:
        if field not in data:
            return f"Missing required field: {field}"

        value = data[field]

        # For this API, required fields must contain text
        if not isinstance(value, str) or not value.strip():
            return f"The field '{field}' must not be empty."

    return None


def validate_course_data(data):
    """
    Validate the fields used to create or update a course.

    Returns:
        str or None: An error message if validation fails, otherwise None.
    """
    required_error = validate_required_fields(data)
    if required_error:
        return required_error

    if data["status"] not in ALLOWED_STATUSES:
        return (
            "Invalid status. Status must be one of: "
            '"Not Started", "In Progress", or "Completed".'
        )

    if not validate_date(data["target_date"]):
        return "target_date must use the format YYYY-MM-DD."

    return None


def get_request_json():
    """
    Safely retrieve JSON data from the request body.

    Returns:
        tuple: (data, error_message)
    """
    data = request.get_json(silent=True)

    if data is None:
        return None, "Request body must contain valid JSON."

    if not isinstance(data, dict):
        return None, "Request body must be a JSON object."

    return data, None


@app.errorhandler(FileStorageError)
def handle_file_storage_error(error):
    """Return a helpful response when a file operation fails."""
    return jsonify({
        "error": str(error)
    }), 500


@app.route("/api/courses", methods=["POST"])
@app.route("/api/courses/", methods=["POST"])
def create_course():
    """
    Create a new course.

    POST /api/courses

    Example request body:
    {
        "name": "Python Basics",
        "description": "Learn the fundamentals of Python.",
        "target_date": "2026-12-31",
        "status": "Not Started"
    }
    """
    data, error = get_request_json()

    if error:
        return jsonify({"error": error}), 400

    validation_error = validate_course_data(data)

    if validation_error:
        return jsonify({"error": validation_error}), 400

    with file_lock:
        courses = load_courses()

        new_course = {
            "id": get_next_course_id(courses),
            "name": data["name"].strip(),
            "description": data["description"].strip(),
            "target_date": data["target_date"],
            "status": data["status"],
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

        courses.append(new_course)
        save_courses(courses)

    return jsonify(new_course), 201


@app.route("/api/courses", methods=["GET"])
@app.route("/api/courses/", methods=["GET"])
def get_all_courses():
    """
    Return all courses.

    GET /api/courses
    """
    with file_lock:
        courses = load_courses()

    return jsonify(courses), 200


@app.route("/api/courses/<int:course_id>", methods=["GET"])
def get_course(course_id):
    """
    Return one course by ID.

    GET /api/courses/1
    """
    with file_lock:
        courses = load_courses()

        course = next(
            (course for course in courses if course.get("id") == course_id),
            None,
        )

    if course is None:
        return jsonify({
            "error": f"Course with ID {course_id} was not found."
        }), 404

    return jsonify(course), 200


@app.route("/api/courses/<int:course_id>", methods=["PUT"])
def update_course(course_id):
    """
    Update an existing course.

    PUT /api/courses/1

    The request may include one or more editable fields:
    {
        "name": "Advanced Python",
        "description": "Learn advanced Python concepts.",
        "target_date": "2027-01-15",
        "status": "In Progress"
    }

    The ID and created_at fields cannot be changed.
    """
    data, error = get_request_json()

    if error:
        return jsonify({"error": error}), 400

    editable_fields = {
        "name",
        "description",
        "target_date",
        "status",
    }

    # Reject attempts to update fields that are not editable
    unexpected_fields = set(data.keys()) - editable_fields

    if unexpected_fields:
        return jsonify({
            "error": (
                "Unknown or non-editable field(s): "
                + ", ".join(sorted(unexpected_fields))
            )
        }), 400

    with file_lock:
        courses = load_courses()

        course = next(
            (course for course in courses if course.get("id") == course_id),
            None,
        )

        if course is None:
            return jsonify({
                "error": f"Course with ID {course_id} was not found."
            }), 404

        # Create a copy representing the course after the update
        updated_course = course.copy()
        updated_course.update(data)

        # Validate the complete updated course
        validation_error = validate_course_data(updated_course)

        if validation_error:
            return jsonify({"error": validation_error}), 400

        # Clean up text fields before saving
        updated_course["name"] = updated_course["name"].strip()
        updated_course["description"] = updated_course["description"].strip()

        # Replace the old course with the updated one
        course_index = courses.index(course)
        courses[course_index] = updated_course

        save_courses(courses)

    return jsonify(updated_course), 200


@app.route("/api/courses/<int:course_id>", methods=["DELETE"])
def delete_course(course_id):
    """
    Delete a course by ID.

    DELETE /api/courses/1
    """
    with file_lock:
        courses = load_courses()

        course = next(
            (course for course in courses if course.get("id") == course_id),
            None,
        )

        if course is None:
            return jsonify({
                "error": f"Course with ID {course_id} was not found."
            }), 404

        courses.remove(course)
        save_courses(courses)

    return jsonify({
        "message": f"Course with ID {course_id} was deleted successfully."
    }), 200


if __name__ == "__main__":
    # Ensure the JSON file exists before starting the server
    initialize_data_file()

    # debug=True is useful during development
    app.run(debug=True)