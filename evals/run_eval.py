# Import json so we can read the evaluation cases
import json

# Import requests so we can send HTTP requests to our API
import requests


# Store the address of our local enrichment endpoint
API_URL = "http://127.0.0.1:8000/enrich"


# Open the evaluation cases file
with open("evals/cases.json", "r", encoding="utf-8") as file:
    # Convert the JSON file into Python data
    cases = json.load(file)


# Keep track of how many fields matched
total_fields = 0

# Keep track of how many fields were correct
matching_fields = 0

# Keep track of failures
failed_cases = []


# Run every evaluation case
for index, case in enumerate(cases, start=1):

    # Print which case is currently being tested
    print(f"\nRunning case {index}/{len(cases)}...")

    # Try to send the property description to our API
    try:
        # Send the property description to the enrichment endpoint
        response = requests.post(
            API_URL,
            json={"text": case["text"]},
            timeout=60,
        )

    # Catch a timeout so one slow case does not stop the whole evaluation
    except requests.exceptions.Timeout:

        # Record this case as a timeout failure
        failed_cases.append(
            {
                "case": index,
                "error": "Evaluation request timed out after 60 seconds",
            }
        )

        # Move to the next evaluation case
        continue

    # Catch other connection errors so the evaluation can continue
    except requests.exceptions.RequestException as error:

        # Record the connection failure
        failed_cases.append(
            {
                "case": index,
                "error": str(error),
            }
        )

        # Move to the next evaluation case
        continue

    # Check whether the API returned a successful response
    if response.status_code != 200:

        # Record the API failure
        failed_cases.append(
            {
                "case": index,
                "error": response.text,
            }
        )

        # Move to the next evaluation case
        continue

    # Convert the API response into Python data
    actual = response.json()

    # Get the expected answer for this case
    expected = case["expected"]

    # Compare the important fields
    for field in expected:

        # Count this field as one evaluation
        total_fields += 1

        # Check whether the API returned the expected value
        if actual.get(field) == expected[field]:

            # Count the field as correct
            matching_fields += 1

        else:

            # Record the mismatch so we can inspect it later
            failed_cases.append(
                {
                    "case": index,
                    "field": field,
                    "expected": expected[field],
                    "actual": actual.get(field),
                }
            )


# Calculate the percentage of correctly matched fields
match_percentage = (
    matching_fields / total_fields * 100
    if total_fields
    else 0
)


# Print the evaluation summary
print("\nEvaluation Results")
print("------------------")
print(f"Cases: {len(cases)}")
print(f"Fields checked: {total_fields}")
print(f"Fields matched: {matching_fields}")
print(f"Match rate: {match_percentage:.1f}%")


# Print failures when there are any
if failed_cases:

    print("\nFailures:")

    # Show every recorded failure
    for failure in failed_cases:
        print(failure)

else:

    # Tell us when every field matched
    print("\nAll evaluation fields matched.")