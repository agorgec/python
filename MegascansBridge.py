import requests
import hou

# Define the Bridge API endpoint
url = "http://localhost:28241/GetMegascansFolder/"
data = None

try:
    # Send a GET request to the Bridge server
    response = requests.get(url, timeout=5)

    # Check if the request was successful (status code 200)
    if response.status_code == 200:
        # Parse the JSON response
        data = response.json()
        print("Response from Megascans Bridge:")
        print(data)
    else:
        warning_1 = f"Failed to get response. Status code: {response.status_code}"
        hou.ui.displayMessage(warning_1, severity=hou.severityType.Warning)
        print(warning_1)

except requests.exceptions.ConnectionError:
    warning_2 = "Error: Could not connect to Megascans Bridge. Ensure it is running."
    hou.ui.displayMessage(warning_2, severity=hou.severityType.Warning)
    print(warning_2)
except requests.exceptions.Timeout:
    warning_3 = "Error: Request timed out. Check Bridge server status."
    hou.ui.displayMessage(warning_3, severity=hou.severityType.Warning)
    print(warning_3)
except Exception as e:
    warning_4 = f"An unexpected error occurred: {e}"
    hou.ui.displayMessage(warning_4, severity=hou.severityType.Warning)
    print(warning_4)

if data:
    node = hou.pwd()
    node.parm("library_path").set(data["folder"])
