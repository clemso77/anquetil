"""
Page management and page definitions
"""

from PIL import Image, ImageDraw, ImageFont
import config


class Page:
    """Base class for display pages"""
    
    def __init__(self, name):
        """
        Initialize a page
        
        Args:
            name: Name of the page
        """
        self.name = name
    
    def render(self):
        """
        Render the page content
        
        Returns:
            PIL Image object
        """
        raise NotImplementedError("Subclasses must implement render()")


class TextPage(Page):
    """Simple page displaying text"""
    
    def __init__(self, name, text, bg_color=(0, 0, 0), text_color=(255, 255, 255)):
        """
        Initialize a text page
        
        Args:
            name: Name of the page
            text: Text to display (can be multiline)
            bg_color: Background color RGB tuple
            text_color: Text color RGB tuple
        """
        super().__init__(name)
        self.text = text
        self.bg_color = bg_color
        self.text_color = text_color
    
    def render(self):
        """Render the text page"""
        # Create image with background color
        image = Image.new('RGB', (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT), self.bg_color)
        draw = ImageDraw.Draw(image)
        
        # Try to use a default font, fallback to bitmap font if not available
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        except (IOError, OSError):
            font = ImageFont.load_default()
        
        # Draw text centered
        # Split text into lines
        lines = self.text.split('\n')
        
        # Calculate total text height
        line_heights = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_heights.append(bbox[3] - bbox[1])
        
        total_height = sum(line_heights) + (len(lines) - 1) * 10  # 10px spacing
        y = (config.DISPLAY_HEIGHT - total_height) // 2
        
        # Draw each line centered
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (config.DISPLAY_WIDTH - text_width) // 2
            draw.text((x, y), line, fill=self.text_color, font=font)
            y += line_heights[i] + 10
        
        return image


class ColorPage(Page):
    """Simple page displaying a solid color"""
    
    def __init__(self, name, color):
        """
        Initialize a color page
        
        Args:
            name: Name of the page
            color: RGB tuple
        """
        super().__init__(name)
        self.color = color
    
    def render(self):
        """Render the color page"""
        return Image.new('RGB', (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT), self.color)


class StatusPage(Page):
    """Status page showing system information"""
    
    def __init__(self, name):
        super().__init__(name)
    
    def render(self):
        """Render status information"""
        import datetime
        
        # Create image
        image = Image.new('RGB', (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT), (20, 20, 40))
        draw = ImageDraw.Draw(image)
        
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        except (IOError, OSError):
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # Get current time
        now = datetime.datetime.now()
        time_str = now.strftime("%H:%M:%S")
        date_str = now.strftime("%Y-%m-%d")
        
        # Draw title
        title = "STATUS"
        bbox = draw.textbbox((0, 0), title, font=font_large)
        title_width = bbox[2] - bbox[0]
        draw.text(((config.DISPLAY_WIDTH - title_width) // 2, 30), title, 
                  fill=(100, 200, 255), font=font_large)
        
        # Draw time
        bbox = draw.textbbox((0, 0), time_str, font=font_large)
        time_width = bbox[2] - bbox[0]
        draw.text(((config.DISPLAY_WIDTH - time_width) // 2, 100), time_str, 
                  fill=(255, 255, 255), font=font_large)
        
        # Draw date
        bbox = draw.textbbox((0, 0), date_str, font=font_small)
        date_width = bbox[2] - bbox[0]
        draw.text(((config.DISPLAY_WIDTH - date_width) // 2, 150), date_str, 
                  fill=(200, 200, 200), font=font_small)
        
        # Draw page indicator
        info = f"Page: {self.name}"
        bbox = draw.textbbox((0, 0), info, font=font_small)
        info_width = bbox[2] - bbox[0]
        draw.text(((config.DISPLAY_WIDTH - info_width) // 2, 200), info, 
                  fill=(150, 150, 150), font=font_small)
        
        return image


class PageManager:
    """Manages multiple pages and page navigation"""
    
    def __init__(self):
        """Initialize the page manager"""
        self.pages = []
        self.current_index = 0
    
    def add_page(self, page):
        """
        Add a page to the manager
        
        Args:
            page: Page object
        """
        self.pages.append(page)
    
    def next_page(self):
        """Switch to the next page"""
        if len(self.pages) > 0:
            self.current_index = (self.current_index + 1) % len(self.pages)
    
    def previous_page(self):
        """Switch to the previous page"""
        if len(self.pages) > 0:
            self.current_index = (self.current_index - 1) % len(self.pages)
    
    def get_current_page(self):
        """
        Get the current page
        
        Returns:
            Current Page object or None if no pages
        """
        if len(self.pages) > 0:
            return self.pages[self.current_index]
        return None
    
    def render_current_page(self):
        """
        Render the current page
        
        Returns:
            PIL Image object or None if no pages
        """
        page = self.get_current_page()
        if page:
            return page.render()
        return None


# Create default pages
def create_default_pages():
    """
    Create a set of default pages for demonstration
    
    Returns:
        PageManager with default pages
    """
    manager = PageManager()
    
    # Page 1: Welcome
    manager.add_page(TextPage(
        "Welcome",
        "Raspberry Pi 5\nTFT Display\nDemo",
        bg_color=(0, 50, 100),
        text_color=(255, 255, 255)
    ))
    
    # Page 2: Status
    manager.add_page(StatusPage("Status"))
    
    # Page 3: Red
    manager.add_page(ColorPage("Red", (255, 0, 0)))
    
    # Page 4: Green
    manager.add_page(ColorPage("Green", (0, 255, 0)))
    
    # Page 5: Blue
    manager.add_page(ColorPage("Blue", (0, 0, 255)))
    
    # Page 6: Info
    manager.add_page(TextPage(
        "Info",
        "Short Press:\nChange Page\n\nLong Press:\nToggle Backlight",
        bg_color=(50, 50, 50),
        text_color=(255, 255, 0)
    ))
    
    return manager
