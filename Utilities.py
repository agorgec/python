import hou
import json
import os


def current_parms_eval(node):
    """
    Evaluate and store current node parameters for quick access.

    This method evaluates node parameters such as the Megascans asset, file format, geometry,
    and resolution, and stores them as attributes for easy retrieval later.
    """
    # Retrieve the user data containing Megascans information
    user_data = node.userDataDict().get("megascans_user_data")

    if user_data:
        # Dictionary mapping parameter names to their attribute names
        parms_to_eval = {
            "megascans_asset": "",
            "file_format": "",
            "render_geo": "",
            "proxy_geo": "",
            "resolution": "",
        }

        # Loop rough parameters and dynamically evaluate and assign them as class attributes
        for parm_name in parms_to_eval.keys():
            # Get parameter menu items
            menu_labels = node.parm(parm_name).menuItems()
            # Get current menu selection index
            menu_index = node.parm(parm_name).eval()
            # Set attribute to selected menu item
            parms_to_eval[parm_name] = menu_labels[
                menu_index
            ]  # Set attribute to selected menu item

        return parms_to_eval


def open_explorer(kwargs):
    """
    Open the file explorer to the current asset's directory if it exists.

    This function retrieves the asset path from the stored Megascans user data and opens the
    file explorer at the asset's directory. If the directory doesn't exist, an error message
    is displayed.
    """
    node = kwargs["node"]
    user_data = node.userDataDict().get("megascans_user_data")

    current_parms_dict = current_parms_eval(node)
    current_asset = current_parms_dict["megascans_asset"]

    if user_data:
        # Extract the asset path from the user data
        directory = json.loads(user_data)[current_asset]["path"]

        # Check if the directory exists and open it in the file explorer
        if os.path.isdir(directory):
            hou.ui.showInFileBrowser(directory)
        else:
            hou.ui.displayMessage(
                "Directory does not exist!"
            )  # Show error if directory is missing
    else:
        hou.ui.displayMessage(
            "User data not found!"
        )  # Show error if user data is missing


def find_id(kwargs):
    """
    Search for an asset by its ID and update the node parameter if found.

    This function searches the 'megascans_asset' parameter for an asset with a matching ID and
    updates the menu to select that asset if it is found. If the asset is not found, an error
    message is displayed.
    """
    node = kwargs["node"]
    # Get the search ID entered by the user
    search_id = node.parm("megascans_id").eval()

    # Get the 'megascans_asset' parameter and its available options (menu labels)
    assets_parm = node.parm("megascans_asset")

    if len(search_id) > 0:
        # Search for an asset whose ID matches the entered search ID
        menu_labels = assets_parm.menuLabels()
        matched_asset = [
            item for item in menu_labels if search_id == item.split("::")[-1]
        ]

        if matched_asset:
            # Set the parameter to the found asset's menu index
            menu_index = menu_labels.index(matched_asset[0])
            assets_parm.set(menu_index)
            assets_parm.pressButton()  # Press the button to refresh the node with the new asset
        else:
            # Display a message if no matching asset was found
            hou.ui.displayMessage("Search ID is not found in menu labels!")
