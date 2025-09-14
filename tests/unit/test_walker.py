import pytest
from jvspatial.core.entities import Node, Walker, on_visit

class TestWalker:
    @pytest.mark.asyncio
    async def test_walker_traversal(self):
        class City(Node):
            name: str = "TestCity"
            
        class Tourist(Walker):
            @on_visit(City)
            async def visit_city(self, city):
                self.response['visited'] = True
                
        city = City()
        tourist = Tourist()
        await tourist.spawn(start=city)
        
        assert tourist.response.get('visited') == True