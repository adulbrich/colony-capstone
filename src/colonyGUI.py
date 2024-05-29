import kivy
from kivy.config import Config
Config.set('input', 'mouse', 'mouse,disable_multitouch')
from kivy.app import App
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scatter import Scatter
from kivy.uix.widget import Widget
from kivy.uix.image import AsyncImage
from kivy.uix.image import Image
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.properties import StringProperty
from kivy.properties import ObjectProperty
from kivy.properties import BooleanProperty
from kivy.graphics import Color, RoundedRectangle
from kivy.graphics.texture import Texture
from kivy.graphics.transformation import Matrix
from kivy.clock import Clock
from kivy.metrics import Metrics
from kivy.properties import StringProperty, ObjectProperty, BooleanProperty, ListProperty
from kivy.factory import Factory
from plyer import filechooser
from count import process_images_from_paths, annotate_image, open_heic
from pillow_heif import register_heif_opener
import os
import time
import csv
import numpy as np
import cv2 as cv
from count import process_images_from_paths, annotate_image
import platform




Config.set('input', 'mouse', 'mouse,multitouch_on_demand')
Config.set('kivy', 'exit_on_escape', '0')

# Set app size
Window.size = (1000, 700)

# Designate our design file
Builder.load_file("style.kv")

# Store list of image containers, each item is a reference to a ImageContainerWidget
imageContainers = []
swap = 1
counter = 0

class ImageContainerWidget(BoxLayout):
    source = StringProperty(None)
    texture = ObjectProperty(None, allownone=True)
    numpy_image = ObjectProperty(comparator=np.array_equal)
    colonies = ObjectProperty(comparator=np.array_equal)
    is_selected = BooleanProperty(False)
    border_color = ListProperty([0, 0, 0, 0])
    process_count = 1
    processed_times = None
    name = StringProperty('')

    def __init__(self, **kwargs):
        super(ImageContainerWidget, self).__init__(**kwargs)
        self.bind(is_selected=self.update_border_color)
        global counter
        counter += 1
        self.id = counter
        self.name = '' #for naming the image
        self.is_selected = False

    def handle_selection(self):
        print(f"Handle selection called for widget with ID: {self.id}")
        self.select_image()

    def select_image(self):
        for container in imageContainers:
            container.is_selected = False
        self.is_selected = True
        self.my_grid_layout.previewer_update(self)
        
    def on_selection(self):
        app = App.get_running_app()
        if not app.root.ids.prevContainer.edited:
            self.is_selected = True
            if self.is_selected:
                self.deselect_others()
                # self.my_grid_layout.previewer_update(self)

    def update_border_color(self, instance, value):
        if self.is_selected:
            self.border_color = [0.1, 0.8, 0.8, 1]  # RGBA for blue
        else:
            self.border_color = [0, 0, 0, 0]  # Reset to transparent

    def deselect_others(self):
        for container in imageContainers:
            if container != self:
                container.is_selected = False


    def remove(self):
        # print("remove is called")
        self.parent.remove_widget(self)
        app = App.get_running_app()
        app.root.handle_delete(self.id)

    
    # Swap image with processed image and back
    def swap_image(self):
        global swap
        if (swap == 0):
            self.ids.swap.clear_widgets()
            replace = AsyncImage(texture = self.texture, size_hint = (1, 1), fit_mode = 'cover')
            self.ids.swap.add_widget(replace)
        else:
            self.ids.swap.clear_widgets()
            replace = AsyncImage(source = self.source, size_hint = (1, 1), fit_mode = 'cover')
            self.ids.swap.add_widget(replace)
    
    def previewer_update(self):
        app = App.get_running_app()
        app.root.previewer_update(self)

class PreviewerContainer(Scatter):
    imgRef = None
    editedColonies = None

    replace = None
    texture = None
    edited = False
    add_mode = False
    remove_mode = False
    if platform.system() == 'Windows':
        hovered = False

        def __init__(self, **kwargs):
            super(PreviewerContainer, self).__init__(**kwargs)
            Window.bind(mouse_pos=self.on_mouse_pos)  # Bind to mouse position changes

        # Change cursor depending on the current mode
        def on_mouse_pos(self, *args):
            pos_old = args[1]  # args[1] is the mouse position

            # Adjust pos depending on users screen scale/density
            pos = (pos_old[0] * Metrics.density, pos_old[1] * Metrics.density)

            inside = self.parent.collide_point(*pos)  # Check if mouse is inside the widget
            if inside:
                if not self.hovered:  # Check if hover state needs to be updated
                    self.hovered = True
                if self.add_mode == True:
                    Window.set_system_cursor('crosshair')
                elif self.remove_mode == True:
                    Window.set_system_cursor('no')
                else:
                    Window.set_system_cursor('arrow')
            else:
                if self.hovered:
                    self.hovered = False
                    Window.set_system_cursor('arrow')

    
    # Implements zoom functionality for previewer image
    # Code inspired from https://stackoverflow.com/questions/49807052/kivy-scroll-to-zoom
    def on_touch_down(self, touch):
        if (self.imgRef is None or self.imgRef.source == None):
            return
        
        # Finds mouse position relative to image and adds/deletes colonies
        global swap
        if ((self.add_mode or self.remove_mode) and touch.is_mouse_scrolling == False and self.parent.collide_point(*touch.pos) and swap == 0):
            mouse_pos = [touch.pos[0], touch.pos[1]]

            if (swap == 0):
                img_size = self.imgRef.texture.size
            else:
                img_size = self.ids.previewer.texture.size

            print(img_size)
            img_ratio = img_size[1]/img_size[0]

            scatter_size = self.ids.previewer.size
            scatter_ratio = scatter_size[1]/scatter_size[0]
            
            if (img_ratio > scatter_ratio):
                img_width = scatter_size[1] / img_ratio
                img_height = scatter_size[1]
            else:
                img_width = scatter_size[0]
                img_height = scatter_size[0] * img_ratio

            change = img_size[0] / img_width

            pos = self.to_local(mouse_pos[0] - ((scatter_size[0] - img_width)/2 * self.scale), mouse_pos[1] - ((scatter_size[1] - img_height)/2 * self.scale))
            pos = [change * pos[0], change * pos[1]]

            if self.add_mode:
                self.add_colony(pos)
            elif len(self.editedColonies[0]) != 0:
                self.remove_colony(pos)
            print("Position relative to image (x,y): ", pos)

        # Zoom in/out and handle moving image
        if touch.is_mouse_scrolling & self.parent.collide_point(*touch.pos):
            factor = None
            if touch.button == 'scrolldown':
                if self.scale < 10:
                    factor = 1.2
            elif touch.button == 'scrollup':
                if self.scale > 1:
                    factor = 1/1.2
            if factor is not None:
                self.apply_transform(Matrix().scale(factor, factor, factor), anchor=touch.pos)
        else:
            super(PreviewerContainer, self).on_touch_down(touch)

    def add_colony(self, pos):
        # Add colony to self.imgRef.colonies at mouse position
        self.edited = True
        array_pos = np.uint16(np.array([[pos[0], pos[1], 5]]))
        self.editedColonies = np.array([np.append(self.editedColonies[0], array_pos, 0)])

        # Update colony counter
        app = App.get_running_app()
        app.root.infoContainer.ids.colony_count_text.text = str(len(self.editedColonies[0]))

        # Update texture being displayed
        proc = annotate_image(np.copy(self.imgRef.numpy_image[0]), self.editedColonies)
        w, h, _ = proc.shape
        texture = Texture.create(size=(h, w))
        texture.blit_buffer(proc.flatten(), colorfmt='rgb', bufferfmt='ubyte')
        self.texture = texture
        self.replace.texture = texture
        # self.imgRef.texture = texture
    
    def remove_colony(self, pos):
        array_pos = np.cfloat(np.array([[pos[0], pos[1]]]))
        colin = np.delete(self.editedColonies[0], 2, 1)    # delete third row of colonies with radius sizes
        colin = colin.astype(float)

        # Find nearest colony to mouse location and delete
        set = colin - array_pos
        distances = np.linalg.norm(set, axis=1)
        idx_of_nearest = np.argsort(distances)[0]

        # Checks if the cursor is within the radius of the nearest colony
        if (distances[idx_of_nearest] < self.editedColonies[0][idx_of_nearest][2] + 1):
            self.edited = True
            self.editedColonies = np.delete(self.editedColonies, idx_of_nearest, 1)

            # Update colony counter
            app = App.get_running_app()
            app.root.infoContainer.ids.colony_count_text.text = str(len(self.editedColonies[0]))

            # Updatetexture being displayed
            proc = annotate_image(np.copy(self.imgRef.numpy_image[0]), self.editedColonies)
            w, h, _ = proc.shape
            texture = Texture.create(size=(h, w))
            texture.blit_buffer(proc.flatten(), colorfmt='rgb', bufferfmt='ubyte')
            self.texture = texture
            self.replace.texture = texture
            # self.imgRef.texture = texture

    def save_changes(self):
        if self.edited:
            self.imgRef.texture = self.texture
            self.imgRef.colonies = self.editedColonies
            self.edited = False

    def undo_changes(self):
        self.texture = self.imgRef.texture
        self.editedColonies = self.imgRef.colonies
        if (swap == 0):
            self.replace.texture = self.texture
        app = App.get_running_app()
        app.root.infoContainer.ids.colony_count_text.text = str(len(self.editedColonies[0]))
        self.edited = False
            
    def zoom_in(self):
        if self.scale < 10:
            self.apply_transform(Matrix().scale(1.2, 1.2, 1.2), anchor=self.parent.center )
    
    def zoom_out(self):
        if self.scale > 1:
            self.apply_transform(Matrix().scale(1/1.2, 1/1.2, 1/1.2), anchor=self.parent.center )

    # Swap image with processed image and back
    def swap_image(self):
        global swap

        if (swap == 0):
            self.ids.relativeContainer.clear_widgets()
            if self.edited:
                self.replace = AsyncImage(texture = self.texture, size = (self.parent.width, self.parent.height), fit_mode = 'contain')
            else:
                self.replace = AsyncImage(texture = self.imgRef.texture, size = (self.parent.width, self.parent.height), fit_mode = 'contain')
            self.ids.relativeContainer.add_widget(self.replace)
        else:
            self.ids.relativeContainer.clear_widgets()
            self.replace = AsyncImage(source = self.imgRef.source, size = (self.parent.width, self.parent.height), fit_mode = 'contain')
            self.ids.relativeContainer.add_widget(self.replace)

    # Set image back to it's original size and position
    def reset_image(self):
        self.scale = 1
        self.pos = self.parent.pos


class InfoContainer(BoxLayout):
    tools_visible = BooleanProperty(False)
    toggle_state = BooleanProperty(True)
    fullscreen_mode = BooleanProperty(False)

    def toggle_tools(self):
        self.tools_visible = not self.tools_visible
        self.update_ui_based_on_tools_visibility()

    def update_ui_based_on_tools_visibility(self):
        
        # when the tools section is turned on
        if self.tools_visible:
            # Hide the edit button
            self.ids.edit_button.size_hint = (None, None)
            self.ids.edit_button.size = (0, 0)
            self.ids.edit_button.opacity = 0

            self.ids.name_input_layout.size_hint = (None, None)
            self.ids.name_input_layout.size = (0, 0)
            self.ids.name_input_layout.opacity = 0

            self.ids.save_name_button.size_hint = (None, None)
            self.ids.save_name_button.size = (0, 0)
            self.ids.save_name_button.opacity = 0

            self.ids.colonies_detected_section.size_hint = (1, 0.033)

            # Show the tool section
            self.ids.tools_layout.size_hint = (1, 0.2)
            self.ids.tools_layout.opacity = 1
            
            app = App.get_running_app()
            app.root.replace_with_save_and_exit()
            if app.root.ids.prevContainer.add_mode:
                self.ids.add_icon.color = (0.1, 0.8, 0.8, 1)
            else:
                self.ids.add_icon.color = (1, 1, 1, 1)
            if app.root.ids.prevContainer.remove_mode:
                self.ids.remove_icon.color = (0.1, 0.8, 0.8, 1)
            else:
                self.ids.remove_icon.color = (1, 1, 1, 1)

        # when the tools section is turned off
        else:
            # Show the edit button
            # self.ids.edit_button.size_hint = (1, 0.05) # (width, heigt)
            self.ids.colonies_detected_section.size_hint = (1, 0.0032)

            self.ids.edit_button.size_hint = (1, 0.004)  
            self.ids.edit_button.opacity = 1

            self.ids.name_input_layout.size_hint = (1, 0.002)  
            self.ids.name_input_layout.opacity = 1

            self.ids.save_name_button.size_hint = (1, 0.003)  
            self.ids.save_name_button.opacity = 1

            # Hide the tool section
            self.ids.tools_layout.size_hint = (None, None)
            self.ids.tools_layout.size = (0, 0)
            self.ids.tools_layout.opacity = 0


    def save_name(self):
        name_input = self.ids.name_input  # Retrieve the TextInput widget by id
        name = name_input.text.strip()  # Get the text from the TextInput widget 
        # Check if there is a selected image container
        selected_container = next((c for c in imageContainers if c.is_selected), None)
        if selected_container:
            selected_container.name = name
            print(f"Saved Name: {name} for image: {selected_container.source}")
    
    def add_colony(self):
        print("Add Colony was pressed")
        app = App.get_running_app()
        app.root.ids.prevContainer.add_mode = not app.root.ids.prevContainer.add_mode
        app.root.ids.prevContainer.remove_mode = False
        if app.root.ids.prevContainer.add_mode:
            self.ids.add_icon.color = (0.1, 0.8, 0.8, 1)
        else:
            self.ids.add_icon.color = (1, 1, 1, 1)
        self.ids.remove_icon.color = (1, 1, 1, 1)
    
    def remove_colony(self):
        app = App.get_running_app()
        app.root.ids.prevContainer.remove_mode = not app.root.ids.prevContainer.remove_mode
        app.root.ids.prevContainer.add_mode = False
        if app.root.ids.prevContainer.remove_mode:
            self.ids.remove_icon.color = (0.1, 0.8, 0.8, 1)
        else:
            self.ids.remove_icon.color = (1, 1, 1, 1)
        self.ids.add_icon.color = (1, 1, 1, 1)
    
    def zoom_in(self):
        print("Zoom In was pressed")


    def zoom_out(self):
        print("Zoom Out was pressed")
    
    def full_screen(self):
        # Get the current running app instance
        app = App.get_running_app()
        self.fullscreen_mode = not self.fullscreen_mode
        # Assuming the root widget is MyGridLayout or has an attribute to access it
        if self.fullscreen_mode:
            print("Full Screen was pressed")
            self.size_hint = (None, 1)
            self.ids.spacer_under_infocontainer.size_hint_y = 0.092
        else:
            print("Exit Full Screen was pressed")
            self.size_hint = (0.4, 0.1)
            self.ids.spacer_under_infocontainer.size_hint_y = 0.01

        if hasattr(app, 'root'):
            my_grid_layout = app.root  # or however you can access MyGridLayout from app
            my_grid_layout.toggle_fullscreen()
        else:
            print("MyGridLayout instance not found")

    
    def switch_toggle(self):
        self.toggle_state = not self.toggle_state
        print("Toggle button was pressed, state is now:", "On" if self.toggle_state else "Off")
    
    
    def remove(self):
        self.parent.remove_widget(self)



class MyGridLayout(Widget):
    fullscreen_mode = BooleanProperty(False)  # Track fullscreen mode state

    def __init__(self, **kwargs):
        super(MyGridLayout, self).__init__(**kwargs)
        self.processing = True  # Flag to indicate if it's processing or exporting
        self.editing = False  # Flag to indicate if the user is editing or not
        self.tempUse = False  # Flag to switch to image when in editing mode after not saving changes
        self.infoContainer = None # Info container
        Window.bind(on_drop_file=self.file_drop)
        Window.bind(on_resize=self.on_window_resize)

    def initialize_window_size(self):
        print("int", Window.width, Window.height)
        return int(75 * min(1000/1920, 700/1000))

    # Adjust fonts with window resize
    def on_window_resize(self, instance, width, height):
        font_size = min(width/1920, height/1000)

        self.ids.upload_button.font_size = int(75 * font_size)
        self.ids.process_button.font_size = int(75 * font_size)
        self.ids.reprocess_button.font_size = int(60 * font_size)
        print(width, height)
        print(Window.size)
        if self.infoContainer != None:
            self.infoContainer.ids.detected_text.font_size = int(40 * font_size)

    # Open the file expolorer when the upload button is pressed
    def file_explorer_or_cancel(self):
        try:
            # current buttton: Upload
            if self.processing:
                filechooser.open_file(on_selection = self.selected, multiple = True)
            # current button: Exit
            elif self.editing:
                if self.ids.prevContainer.edited:
                    Factory.SaveChangesPopup().open()
                else:
                    self.activate_exit()
            # current button:Cancel
            else:
                self.activate_cancel()
        except Exception as e:
            print(f"Error: {e}")
        
    
    # Send dropped in images to load_image()
    def file_drop(self, window, file_path, x, y): 
        file_path = str(file_path.decode("utf-8"))
        self.load_image(file_path)

    # Send selected images to load_image()
    def selected(self, selection):
        if selection:
            for i in range(len(selection)):
                self.load_image(selection[i])

    # Add provided image to our image_box section add put in the image previewer
    def load_image(self, file_path):
        if file_path.lower().endswith(('.png', '.jpg', '.jpeg', 'heic')):
            if file_path.lower().endswith('heic'):
                register_heif_opener()
            imageContainer = ImageContainerWidget(source = file_path, texture = None, numpy_image = None, colonies = None)
            imageContainers.append(imageContainer)
            self.ids.image_box.add_widget(imageContainer)

            # Set a reference to this MyGridLayout instance on the new ImageContainerWidget
            imageContainer.my_grid_layout = self

            for container in imageContainers[:-1]:  # Exclude the last one, which is the newly added
                container.is_selected = False

            # Select the last added image
            imageContainers[-1].is_selected = True 

            self.ids.prevContainer.imgRef = imageContainers[-1]
            self.ids.prevContainer.ids.previewer.source = file_path
            if (self.ids.prevContainer.replace != None):
                self.ids.prevContainer.replace.source = file_path
                self.ids.prevContainer.opacity = 1

            self.ids.prevContainer.opacity = 1
            self.ids.process_times_input_layout.opacity = 1
            print(imageContainers)
        else:
            print("Could not open")
    
    # Update Image in the image previewer
    def previewer_update(self, imgReference):
        global swap

        container = self.ids.prevContainer 
        if not container.edited:
            container.reset_image()
            container.imgRef = imgReference

            if imgReference.colonies is not None:
                self.infoContainer.ids.colony_count_text.text = str(len(imgReference.colonies[0]))
                container.editedColonies = imgReference.colonies
            if container.replace is None:
                container.ids.previewer.source = imgReference.source
            else:
                if swap == 1:
                    container.replace.source = imgReference.source
                else:
                    container.replace.texture = imgReference.texture
            self.ids.process_times.text = str(container.imgRef.process_count)

            # Update the name input field with the name of the selected image
            self.infoContainer.ids.name_input.text = imgReference.name
        else:
            self.tempPrev = imgReference
            self.tempUse = True
            Factory.SaveChangesPopup().open()


    def handle_delete(self, id):
        print(len(imageContainers))

        # Remove from imageContainers
        for i in range(len(imageContainers)):
            print("image: ", imageContainers[i], "id: ", imageContainers[i].id)
            if (imageContainers[i].id == id):
                if imageContainers[i].is_selected and len(imageContainers) != 1:
                    if i == len(imageContainers) - 1:
                        imageContainers[-2].is_selected = True
                        self.previewer_update(imageContainers[-2])
                    else:
                        imageContainers[-1].is_selected = True
                        self.previewer_update(imageContainers[-1])
                del imageContainers[i]
                break

        if len(imageContainers) == 0:
            self.ids.prevContainer.opacity = 0
            self.ids.process_times_input_layout.opacity = 0
            self.ids.process_times.text = "1"
            if not self.processing:
                self.activate_cancel()            

    def activate_cancel(self):
        self.ids.process_button.text = "Process"
        self.ids.upload_button.text = "Upload"
        self.processing = True
        if (swap == 0):
            self.toggle_images()
        self.infoContainer.remove()
        self.remove_reprocess_button()
        self.ids.prevContainer.reset_image()

    def activate_exit(self):
        self.ids.process_button.text = "Export"
        self.ids.upload_button.text = "Cancel"
        self.add_reprocess_button()
        self.editing = False
        
        self.infoContainer.toggle_tools()
        if (swap == 1):
            self.toggle_images()
            self.infoContainer.switch_toggle()
        # self.previewer_update(self.ids.prevContainer.imgRef)
        self.ids.prevContainer.edited = False
        self.ids.prevContainer.undo_changes()
        if self.tempUse:
            self.tempUse = False
            self.tempPrev.on_selection()
            self.previewer_update(self.tempPrev)
        self.ids.prevContainer.add_mode = False
        self.ids.prevContainer.remove_mode = False
        self.ids.prevContainer.reset_image()



    def convert_to_texture(self, image):
        w, h, _ = image.shape
        texture = Texture.create(size=(h, w))
        texture.blit_buffer(image.flatten(), colorfmt='rgb', bufferfmt='ubyte')

        return texture
    
    def reprocess_image(self):
        if self.ids.prevContainer.imgRef.processed_times != self.ids.prevContainer.imgRef.process_count:
            print("reprocessed")
            self.ids.prevContainer.imgRef.texture = None
            self.activate_cancel()
            self.on_process_button_press()
        else:
            print("not reprocessed")
    
    def start_processing(self):
        print("Processing started...")

        for container in imageContainers:
            if(container.texture == None):
                print("proc count: ", container.process_count)
                container.processed_times = container.process_count
                colonies, numpyImage = process_images_from_paths([container.source])
                if colonies[0] is not None:
                    container.texture = self.convert_to_texture(annotate_image(np.copy(numpyImage[0]), colonies[0]))
                else:
                    container.texture = self.convert_to_texture(numpyImage[0])
                container.numpy_image = numpyImage
                if colonies[0] is not None:
                    container.colonies = colonies[0]
                else: 
                    # Create empty colonies array when 0 colonies detected
                    container.colonies = np.uint16(np.empty((1,0,3)))

        if (len(imageContainers) != 0):
            self.infoContainer = InfoContainer()
            self.ids.right_side_layout.add_widget(self.infoContainer)
            self.infoContainer.ids.detected_text.font_size = int(40 * Window.size[0]/1920)
            self.infoContainer.ids.colony_count_text.text = str(len(self.ids.prevContainer.imgRef.colonies[0]))
            self.ids.prevContainer.editedColonies = self.ids.prevContainer.imgRef.colonies
            self.toggle_images()


    def export_photos(self):
        print("Export Photo button was clicked.")
        directory_path = filechooser.choose_dir(title="Select Export Directory")
        if directory_path:
            timestamp = time.strftime("%Y%m%d-%H%M%S")

            for i, container in enumerate(imageContainers):
                if container.texture:  # Check if the image is processed
                    if container.name:  # Use the custom name if provided
                        file_name = f"{container.name}_{timestamp}.png"
                    else:  # Fallback to default naming convention
                        file_name = f"processed_image_{i}_{timestamp}.png"

                    file_path = os.path.join(directory_path[0], file_name)
                    self.save_texture_to_file(container.texture, file_path)
                    print(f"Exported {file_path}")



    def export_csv(self):
        print("Export CSV button was clicked.")
        directory_path = filechooser.choose_dir(title="Select Export Directory")
        if directory_path:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            colony_counts = []
            for i, container in enumerate(imageContainers):
                if container.texture:  # Ensure the image is processed
                    default_image_name = f"processed_image_{i}_{timestamp}.png"
                    unique_image_name = container.name if container.name else "N/A"
                    # Collect image names and colony count
                    colony_counts.append((default_image_name, unique_image_name, len(container.colonies[0])))
            # Generate and save the CSV file
            self.save_colony_data_to_csv(colony_counts, directory_path[0], timestamp)
        
    def save_colony_data_to_csv(self, colony_data, directory_path, timestamp):
        # Define the CSV file path
        csv_file_path = os.path.join(directory_path, f"colony_counts_{timestamp}.csv")
        with open(csv_file_path, mode='w', newline='') as file:
            writer = csv.writer(file)
            # Write the header
            writer.writerow(['Default Image Name', 'Unique Image Name', 'Colony Count'])
            # Write the data
            for default_image_name, unique_image_name, count in colony_data:
                writer.writerow([default_image_name, unique_image_name, count])
        print(f"CSV file saved at {csv_file_path}")
     

    def save_texture_to_file(self, texture, file_path):
        if texture is not None:
            image_data = bytes(texture.pixels)
            image_size = (texture.width, texture.height)
            from PIL import Image
            image = Image.frombytes('RGBA', image_size, image_data, 'raw', 'RGBA', 0, -1)
            image.save(file_path)


    def replace_with_export_and_cancel(self):
        self.ids.process_button.text = "Export"
        self.ids.upload_button.text = "Cancel"
        self.add_reprocess_button()
        self.processing = False

    def replace_with_save_and_exit(self):
        self.ids.process_button.text = "Save"
        self.ids.upload_button.text = "Exit"
        self.remove_reprocess_button()
        self.editing = True

    def add_reprocess_button(self):
        self.ids.reprocess_button.parent.opacity = 1
        self.ids.reprocess_button.parent.size_hint = (1, 1)
        self.ids.upload_button.parent.padding = (20, 0, 10, 0)
        self.ids.process_button.parent.padding = (10, 0, 20, 0)
        self.ids.upload_process_container.padding = (0, 0, 180, 0)

    def remove_reprocess_button(self):
        self.ids.reprocess_button.parent.opacity = 0
        self.ids.reprocess_button.parent.size_hint = (0, 0)
        self.ids.upload_button.parent.padding = (180, 0, 40, 0)
        self.ids.process_button.parent.padding = (40, 0, 180, 0)
        self.ids.upload_process_container.padding = (0, 0, 0, 0)

    # Process/Export/Save buttons
    def on_process_button_press(self):
        try:
            # Current button: Process button
            if self.processing:
                if len(imageContainers) != 0:
                    self.start_processing()
                    self.replace_with_export_and_cancel()
                    self.ids.prevContainer.reset_image()
            # Current button: Save button
            elif self.editing:
                print("saving")
                # self.infoContainer.toggle_tools()
                # self.ids.prevContainer.reset_image()
                self.ids.prevContainer.save_changes()
                self.activate_exit()
            # Current button: Export button
            else:
                Factory.ExportOptionsPopup().open()
        except Exception as e:
            print(f"Error: {e}")

    def toggle_fullscreen(self):
        self.fullscreen_mode = not self.fullscreen_mode
        # app = App.get_running_app()
        # info_container = app.root.ids.info_container

        if self.fullscreen_mode:
            # Enter fullscreen mode

            self.ids.image_scroll_view.size_hint = (0, 0)  # Hide image list
            self.ids.upload_process_container.size_hint = (0,0)
            self.ids.upload_button.opacity = 0
            self.ids.upload_button.text = ""
            self.ids.process_button.opacity = 0
            self.ids.process_button.text = ""
            self.ids.process_times_input_layout.opacity = 0
            self.ids.prevContainer.reset_image()
            
        else:
            # Exit fullscreen mode, restore original layout
            self.ids.image_scroll_view.size_hint = (0.4, 1)
            self.ids.upload_process_container.size_hint = (1,0.3)
            self.ids.upload_button.opacity = 1
            self.ids.upload_button.text = "Exit"
            self.ids.process_button.opacity = 1
            self.ids.process_button.text = "Save"
            self.ids.process_times_input_layout.opacity = 1
            self.ids.prevContainer.reset_image()
    
    # Toggle images between processed and non-processed versions
    def toggle_images(self):
        global swap
        if (swap == 0):
            swap = 1
        else:
            swap = 0

        for container in imageContainers:
            container.swap_image()
        
        # Toggle image in container to unprocessed/processed
        self.ids.prevContainer.swap_image()

# buttons in tools section
class ImageButton(ButtonBehavior, Image):
    def __init__(self, **kwargs):
        super(ImageButton, self).__init__(**kwargs)
        self.hovered = False  # Attribute to track hover state
        Window.bind(mouse_pos=self.on_mouse_pos)  # Bind to mouse position changes

    # this function called whenever the mouse position changes
    def on_mouse_pos(self, *args):
        # Mac
        pos = args[1]  # args[1] is the mouse position

        # Adjust pos depending on user's screen scale/density if on Windows
        if platform.system() == 'Windows':
            pos = (pos[0] * Metrics.density, pos[1] * Metrics.density)

        inside = self.collide_point(*self.to_widget(*pos))  # Check if mouse is inside the widget
        if inside:
            if not self.hovered:  # Check if hover state needs to be updated
                self.hovered = True
                self.on_cursor_enter()
        else:
            if self.hovered:
                self.hovered = False
                self.on_cursor_leave()

    def on_cursor_enter(self):
        print("cursor on: image")
        # self.color.rgb = (0.7, 0.7, 0.7,1)  
        Window.set_system_cursor('hand')

    def on_cursor_leave(self):
        print("cursor off:image")
        # self.color = (1, 1, 1,1)
        Window.set_system_cursor('arrow')

    def on_press(self):
        super(ImageButton, self).on_press()
        # Temporarily change the color tint to indicate a highlight
        if (self.source != "img/add_icon.png" and self.source != "img/remove_icon.png"):
            self.color = (0.1, 0.8, 0.8, 1)
            Clock.schedule_once(self.remove_highlight, 0.3)

    def remove_highlight(self, *args):
        # Revert to the original color tint
        self.color = (1, 1, 1, 1)

    def on_parent(self, instance, value):
        # Unbind from mouse_pos when the widget is removed from its parent
        if value is None:
            Window.unbind(mouse_pos=self.on_mouse_pos)

class DefaultButton(ButtonBehavior, Label):
    def __init__(self, **kwargs):
        super(DefaultButton, self).__init__(**kwargs)
        self.hovered = False  # Initialize the hovered attribute here
        Window.bind(mouse_pos=self.on_mouse_pos)  # Bind to mouse position changes

        # Default visual style
        self.font_size = 80
        self.size_hint = (1, 0.5)
        self.background_color = (0.5, 0.5, 0.5, 0)  # Makes the default button background transparent
        
        # Custom drawing instructions for the button
        with self.canvas.before:
            Color(rgba=(0.3, 0.3, 0.3, 1))  # Button color
            self.rect = RoundedRectangle(size=self.size, pos=self.pos, radius=[30])
            self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def on_mouse_pos(self, *args):
        pos = args[1]  # args[1] is the mouse position

        # Adjust pos depending on user's screen scale/density if on Windows
        if platform.system() == 'Windows':
            pos = (pos[0] * Metrics.density, pos[1] * Metrics.density)
        
        inside = self.collide_point(*self.to_widget(*pos))  # Check if mouse is inside the widget
        if inside:
            if not self.hovered:  # Check if hover state needs to be updated
                self.hovered = True
                self.on_cursor_enter()
        else:
            if self.hovered:
                self.hovered = False
                self.on_cursor_leave()

    def on_cursor_enter(self):
        print("cursor on")
        Window.set_system_cursor('hand')

    def on_cursor_leave(self):
        print("cursor off")
        Window.set_system_cursor('arrow')

    def on_press(self):
        super(DefaultButton, self).on_press()
        # Temporarily change the color tint to indicate a highlight
        self.color = (0.1, 0.8, 0.8, 1)
        Clock.schedule_once(self.remove_highlight, 0.3)

    def remove_highlight(self, *args):
        self.color = (1, 1, 1, 1)

    def on_parent(self, instance, value):
        # Unbind from mouse_pos when the widget is removed from its parent
        if value is None:
            Window.unbind(mouse_pos=self.on_mouse_pos)

# Inspired from https://stackoverflow.com/questions/62155421/python-kivy-limit-input-values-between-two-numbers-with-a-textinput-filter
# Input for number of processes done to an image
class CountInput(TextInput):
    
    def __init__(self, **kwargs):
        super(CountInput, self).__init__(**kwargs)
        self.bind(text=self.on_text)
        self.bind(focus=self.on_focus)
    
    def on_text(self, instance, value):
        app = App.get_running_app()
        if (value != ''):
            if hasattr(app.root, 'ids') and hasattr(app.root.ids.prevContainer.imgRef, 'process_count'):
                app.root.ids.prevContainer.imgRef.process_count = int(value)
                print("set val: ", app.root.ids.prevContainer.imgRef.process_count)

    def on_focus(self, instance, value):
        if self.text == "" and value == False:
            self.text = "1"
    
    def insert_text(self, substring, from_undo=False):
        if substring in "0,1,2,3,4,5,6,7,8,9":
            cc, cr = self.cursor
            text = self._lines[cr]
            new_text = text[:cc] + substring + text[cc:]
            if int(new_text) > 8:
                return
            elif int(new_text) < 1:
                return
            else:
                super(CountInput, self).insert_text(substring, from_undo=from_undo)



class CustomLayout(BoxLayout):
    pass


class colonyGUI(App):
    def build(self):
        self.myLayout = MyGridLayout()
        return self.myLayout
    
    
if __name__ == '__main__':
    colonyGUI().run()