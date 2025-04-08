import json
from importlib import reload
from collections import namedtuple
from pathlib import Path
import requests
import hou
import nodegraphutils
import MegascansData

reload(MegascansData)


def get_current_paths(node):
    """Extracts selected paths from the HDA."""
    library_path = Path(node.parm("library_path").evalAsString())

    CurrentPaths = namedtuple(
        "CurrentPaths",
        ["library_path", "assets_data_path", "user_data_path", "hash_path"],
    )

    return CurrentPaths(
        library_path,
        library_path / "Downloaded" / "assetsData.json",
        library_path / "megascans_user_data.json",
        library_path / "megascans_user_data.hash",
    )


def get_current_parms(node):
    """Extracts selected menu items and toggle states from the HDA."""

    # Menu-type parameters (with options)
    menu_parms = [
        "megascans_asset",
        "file_format",
        "render_geo",
        "proxy_geo",
        "resolution",
    ]
    menu_values = {
        name: node.parm(name).menuItems()[node.parm(name).eval()] for name in menu_parms
    }

    # Toggle (boolean) parameters
    toggle_parms = ["show_background_image", "save_shader_state", "load_original"]
    toggle_values = {name: node.parm(name).eval() for name in toggle_parms}

    # Combine all parameters
    all_parms = {**menu_values, **toggle_values}
    CurrentParms = namedtuple("CurrentParms", all_parms.keys())

    return CurrentParms(**all_parms)


def open_explorer(kwargs):
    """
    Open the file explorer to the current asset's directory if it exists.

    This function retrieves the asset path from the stored Megascans user data and opens the
    file explorer at the asset's directory. If the directory doesn't exist, an error message
    is displayed.
    """
    node = kwargs["node"]

    asset_info = node.parm("asset_info").evalAsString()

    try:
        # Extract the asset path from the user data
        directory = json.loads(asset_info)["path"]
        # Check if the directory exists and open it in the file explorer
        hou.ui.showInFileBrowser(directory)

    except json.decoder.JSONDecodeError:
        hou.ui.displayMessage(
            "Directory does not exist!"
        )  # Show error if directory is missing


def generate_batch_process(node):
    """
    Search for an asset by its ID and update the node parameter if found.

    This function searches the 'megascans_asset' parameter for an asset with a matching ID and
    updates the menu to select that asset if it is found. If the asset is not found, an error
    message is displayed.
    """
    # Get the search ID entered by the user
    search_parm = node.parm("batch_ids").eval()

    # Get the 'megascans_asset' parameter and its available options (menu labels)
    assets_menu = node.parm("megascans_asset")
    batch_assets = []

    unknown_assets = []

    if len(search_parm) > 0:
        # Search for an asset whose ID matches the entered search ID
        for asset_id in search_parm.split():
            menu_labels = assets_menu.menuLabels()
            matched_asset = [
                asset_id for item in menu_labels if asset_id == item.split("::")[-1]
            ]

            if matched_asset:
                # Set the parameter to the found asset's menu index
                batch_assets.append(matched_asset[0])

            else:
                # If no matching asset is found, add it to the unknown assets list
                unknown_assets.append(asset_id)

        # Display a message if no matching asset was found
        if unknown_assets:
            hou.ui.displayMessage(f"{asset_id} is not found in menu labels!")

        if batch_assets:
            return batch_assets  # If no assets were found, set the parameter to the first asset in the me


def get_asset_preview(node, megascans_user_data):
    """Fetches the preview image path for the currently selected Megascans asset."""
    preview = None

    current_parms = get_current_parms(node)
    if megascans_user_data:
        preview = megascans_user_data.get(current_parms.megascans_asset, {}).get(
            "preview"
        )

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


def add_background_image(node, pane, preview):
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
    pane.setBackgroundImages(images)
    if images:
        nodegraphutils.saveBackgroundImages(pane.pwd(), images)


def show_background_image(node, megascans_user_data=None):
    """
    Adds or removes a background image in the NetworkEditor
    based on the 'show_background_image' parameter.
    """
    current_paths = get_current_paths(node)
    if megascans_user_data is None and current_paths.user_data_path.exists():
        with open(current_paths.user_data_path, "r", encoding="utf-8") as f:
            megascans_user_data = json.load(f)

    preview, old_preview = get_asset_preview(node, megascans_user_data)
    panes = find_network_editors(node)

    if node.parm("show_background_image").eval():
        for pane in panes:
            if old_preview:
                remove_background_image(pane, old_preview)
            if preview:
                add_background_image(node, pane, preview)
    else:
        for pane in panes:
            remove_background_image(pane, preview)


def dump_info(node, megascans_data):
    info_parm = node.parm("asset_info")
    info_parm.lock(False)
    info_parm.revertToDefaults()
    if megascans_data:
        current_parms = get_current_parms(node)
        if current_parms.megascans_asset == "-----":
            return None
        asset_metadata = megascans_data[current_parms.megascans_asset]
        node.parm("has_high").set(0)

        if "high" in [x.lower() for x in asset_metadata["lods"]]:
            node.parm("has_high").set(1)
        info_parm.set(json.dumps(asset_metadata, indent=4))
        info_parm.lock(True)
        return asset_metadata

    return None


def bridge_connect(kwargs):
    # Define the Bridge API endpoint
    node = kwargs["node"]
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
        warning_2 = (
            "Error: Could not connect to Megascans Bridge. Ensure it is running."
        )
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
        node.parm("library_path").set(data["folder"])
        MegascansData.init_hda(node)
