import hou
import json
import os
import nodegraphutils


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
    search_id = node.parm("batch_ids").eval()

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


def get_asset_preview(node):
    """Fetches the preview image path for the currently selected Megascans asset."""
    user_data = node.userDataDict().get("megascans_user_data")

    if not user_data:
        return None

    current_parms_dict = current_parms_eval(node)
    current_asset = current_parms_dict.get("megascans_asset")
    preview = json.loads(user_data).get(current_asset, {}).get("preview")

    asset_metadata = node.parm("asset_info").evalAsString()
    if not asset_metadata:
        return preview, None

    old_preview = json.loads(asset_metadata).get("preview")

    return preview, old_preview


def find_network_editors(node):
    """Finds NetworkEditor panes displaying the node's parent."""
    return [
        pane
        for pane in hou.ui.paneTabs()
        if isinstance(pane, hou.NetworkEditor) and pane.pwd() == node.parent()
    ]


def add_background_image(pane, node, preview):
    """Adds the preview image as a background in the given NetworkEditor pane."""
    bounds = hou.BoundingRect(-1, -1, 1, 1)
    bounds.translate(hou.Vector2(0.5, 1))  # Position adjustment

    image = hou.NetworkImage()
    image.setPath(preview)
    image.setRect(bounds)
    image.setRelativeToPath(node.path())

    pane.setBackgroundImages(list(pane.backgroundImages()) + [image])
    nodegraphutils.saveBackgroundImages(pane.pwd(), pane.backgroundImages())


def remove_background_image(pane, preview):
    """Removes the preview image from the given NetworkEditor pane."""
    images = [img for img in pane.backgroundImages() if img.path() != preview]
    if images:
        pane.setBackgroundImages(images)
        nodegraphutils.saveBackgroundImages(pane.pwd(), images)


def show_background_image(node):
    """
    Adds or removes a background image in the NetworkEditor
    based on the 'show_background_image' parameter.
    """
    if not get_asset_preview(node):
        return None

    preview, old_preview = get_asset_preview(node)
    panes = find_network_editors(node)

    if node.parm("show_background_image").eval():
        for pane in panes:
            if old_preview:
                remove_background_image(pane, old_preview)
            add_background_image(pane, node, preview)
    else:
        for pane in panes:
            remove_background_image(pane, preview)
